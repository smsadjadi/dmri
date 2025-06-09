"""
Nipype conversion of the original FSL‐based Bash pipeline
========================================================
This script recreates the original multi‑subject diffusion‑MRI workflow in a
reproducible Nipype pipeline.  Key improvements over the Bash version
--------------------------------------------------------------------
* **Modularity** – each logical block is encapsulated in a `Node`, making the
  graph easy to modify and debug.
* **Parallel execution** – the workflow is trivially parallelised across
  subjects and, where possible, within subjects via Nipype’s
  MultiProc/SLURM plugins.
* **Caching / resume** – completed nodes are not recomputed; failed nodes can
  be resumed after fixing the issue.
* **Provenance** – Nipype automatically stores a rich provenance record for
  every node, aiding reproducibility.
* **Crash‑files** – on errors, each node produces a `crashfile` with the full
  traceback.

Usage
-----
>>> python nipype_pipeline.py /path/to/dataset  \
...                       --subjects subj_02 subj_03  \
...                       --do_tract 1  \
...                       --matrix_mode 1  \
...                       --nsamples 5000  \
...                       --n_procs 16

If you run on a cluster, swap ``--n_procs`` for the SLURM plugin (see bottom).

Requirements
~~~~~~~~~~~~
* FSL ≥ 6.0 (configured in ``FSLDIR``)  
* Nipype ≥ 1.8  
* Python ≥ 3.8  
* ``jq`` script from the original pipeline has been replaced by Nipype’s JSON
  helpers.

"""

import argparse
import json
import os
from pathlib import Path

from nipype import MapNode, Node, Workflow
from nipype.interfaces import fsl, io as nio, utility as niu
from nipype.interfaces.base import CommandLine

################################################################################
# ----------------------------  Helper Functions  ---------------------------- #
################################################################################

def create_acqparams(datadir: Path, dwi_json: Path, out_file: Path):
    """Re‑implementation of the Bash acqparams generator for TOPUP.

    Parameters
    ----------
    datadir : Path
        Subject working directory.
    dwi_json : Path
        JSON side‑car of the input DWI.
    out_file : Path
        Target text‑file to write.
    """
    with open(dwi_json) as f:
        meta = json.load(f)

    dwell = meta.get("TotalReadoutTime")
    if dwell is None:
        es = meta["EffectiveEchoSpacing"]
        pe_dir = meta["PhaseEncodingDirection"]
        dim_pe = meta["AcquisitionMatrixPE"]  # fall‑back
        dwell = es * (dim_pe - 1)
    nvols_topup = 2  # one AP, one PA
    lines = []
    for v in range(nvols_topup):
        if v == 0:
            lines.append(f"0 -1 0 {dwell}")
        else:
            lines.append(f"0 1 0 {dwell}")
    out_file.write_text("\n".join(lines))
    return str(out_file)


def dot_to_csv(in_file: str, out_file: str):
    """Wrapper around the project’s dot‑to‑CSV converter."""
    import subprocess
    script_dir = Path(__file__).resolve().parent / "tractography" / "dot_to_matrix.py"
    subprocess.check_call(["python", str(script_dir), in_file, out_file])
    return out_file

################################################################################
# ---------------------------  Argument parsing  ----------------------------- #
################################################################################

parser = argparse.ArgumentParser(description="Multi‑subject diffusion Nipype pipeline")
parser.add_argument("dataset", type=Path, help="Root dataset directory containing subject folders")
parser.add_argument("--subjects", nargs="*", default=None, help="Explicit subject list; defaults to all folders")
parser.add_argument("--skip_on_eddy_fail", type=int, default=0, help="Skip subject if eddy fails (1) or continue (0)")
parser.add_argument("--do_tract", type=int, default=1, help="Run tractography")
parser.add_argument("--matrix_mode", type=int, choices=[1, 2, 3, 4], default=1)
parser.add_argument("--nsamples", type=int, default=5000)
parser.add_argument("--n_procs", type=int, default=8, help="#cores for MultiProc plugin")
args = parser.parse_args()

################################################################################
# ------------------------------  Boilerplate  ------------------------------- #
################################################################################

dataset = args.dataset.resolve()
subjects = args.subjects or sorted([p.name for p in dataset.iterdir() if p.is_dir()])
out_root = dataset / "nipype_out"
out_root.mkdir(exist_ok=True)

WF = Workflow(name="dwi_pipeline", base_dir=str(out_root))

infosource = Node(niu.IdentityInterface(fields=["subject_id"]), name="infosource")
infosource.iterables = [("subject_id", subjects)]

# Template paths inside each subject directory
templates = {
    "dwi": "{subject_id}/DTI-Mono_noPAT.nii.gz",
    "dwi_json": "{subject_id}/DTI-Mono_noPAT.json",
    "bval": "{subject_id}/DTI-Mono_noPAT.bval",
    "bvec": "{subject_id}/DTI-Mono_noPAT.bvec",
    "topup_ap": "{subject_id}/ap_b0.nii.gz",
    "topup_pa": "{subject_id}/pa_b0.nii.gz",
    "gre_mag": "{subject_id}/gre_field_mapping_2mm_e1.nii.gz",
    "gre_phase": "{subject_id}/gre_field_mapping_2mm_e2.nii.gz",
    "t1": "{subject_id}/t1_mprage_tra.nii.gz",
}

selectfiles = Node(
    nio.SelectFiles(templates, base_directory=str(dataset)), name="selectfiles"
)

################################################################################
# ------------------------------  Field‑map ---------------------------------- #
################################################################################

prepare_fmap = Node(
    fsl.PrepareFieldmap(scanner="SIEMENS"), name="prepare_fmap"
)
WF.connect(infosource, "subject_id", prepare_fmap, "out_base_name")
WF.connect(selectfiles, "gre_phase", prepare_fmap, "in_phase")
WF.connect(selectfiles, "gre_mag", prepare_fmap, "in_magnitude")
prepare_fmap.inputs.delta_TE = 2.46

################################################################################
# -------------------------------  DWI Preproc ------------------------------- #
################################################################################

# Extract B0 and BET
b0 = Node(fsl.ExtractROI(t_min=0, t_size=1), name="b0")
WF.connect(selectfiles, "dwi", b0, "in_file")

bet_b0 = Node(fsl.BET(frac=0.3, mask=True), name="bet_b0")
WF.connect(b0, "roi_file", bet_b0, "in_file")

# Resample fieldmap to DWI grid using FLIRT (sform)
fmap_resamp = Node(
    fsl.FLIRT(apply_xfm=True, uses_qform=True), name="fmap_resamp"
)
WF.connect(prepare_fmap, "out_fieldmap", fmap_resamp, "in_file")
WF.connect(b0, "roi_file", fmap_resamp, "reference")

# FUGUE unwarping
fugue = Node(fsl.FUGUE(unwarp_direction="z"), name="fugue")
WF.connect(selectfiles, "dwi", fugue, "in_file")
WF.connect(fmap_resamp, "out_file", fugue, "fmap_in_file")
WF.connect(bet_b0, "mask_file", fugue, "mask_file")

# TOPUP block -------------------------------------------------------------

topup_merge = Node(fsl.Merge(dimension="t"), name="topup_merge")
WF.connect(selectfiles, "topup_ap", topup_merge, "in_files")
WF.connect(selectfiles, "topup_pa", topup_merge, "in_files")

topup = Node(fsl.Topup(config="b02b0.cnf"), name="topup")
WF.connect(topup_merge, "merged_file", topup, "in_file")

# ACQP params file (custom Function)
acqparams = Node(
    niu.Function(
        input_names=["datadir", "dwi_json", "out_file"],
        output_names=["acqp_txt"],
        function=create_acqparams,
    ),
    name="acqparams",
)
WF.connect(infosource, ("subject_id", lambda s: str(dataset / s)), acqparams, "datadir")
WF.connect(selectfiles, "dwi_json", acqparams, "dwi_json")
acqparams.inputs.out_file = "acqparams.txt"

# EDDY -------------------------------------------------------------
eddy = Node(fsl.Eddy(), name="eddy")
WF.connect(fugue, "unwarped_file", eddy, "in_file")
WF.connect(bet_b0, "mask_file", eddy, "in_mask")
WF.connect(selectfiles, "bvec", eddy, "in_bvec")
WF.connect(selectfiles, "bval", eddy, "in_bval")
WF.connect(topup, "out_field", eddy, "field")
WF.connect(acqparams, "acqp_txt", eddy, "in_acqp")

# DTIFIT -------------------------------------------------------------
dtifit = Node(fsl.DTIFit(), name="dtifit")
WF.connect(eddy, "out_corrected", dtifit, "dwi")
WF.connect(bet_b0, "mask_file", dtifit, "mask")
WF.connect(selectfiles, "bvec", dtifit, "bvecs")
WF.connect(selectfiles, "bval", dtifit, "bvals")

################################################################################
# ------------------  T1 & Atlas registration to DWI ------------------------ #
################################################################################

flirt_t1 = Node(fsl.FLIRT(dof=6), name="flirt_t1")
WF.connect(selectfiles, "t1", flirt_t1, "in_file")
WF.connect(b0, "roi_file", flirt_t1, "reference")

atlas_path = Path(__file__).resolve().parent / "atlases" / "BN_Atlas_246_2mm.nii.gz"
flirt_atlas = Node(
    fsl.FLIRT(apply_xfm=True, uses_qform=True, in_file=str(atlas_path)), name="flirt_atlas"
)
WF.connect(b0, "roi_file", flirt_atlas, "reference")

################################################################################
# ---------------------------  ROI Generation  ------------------------------ #
################################################################################

make_roi_fn = """
from pathlib import Path
from nipype.interfaces.base import TraitedSpec, File, BaseInterfaceInputSpec, SimpleInterface
import subprocess

class MakeROI(SimpleInterface):
    input_spec = BaseInterfaceInputSpec
    output_spec = TraitedSpec(roi_list=File(exists=True), seed_mask=File(exists=True))

    def _run_interface(self, runtime):
        import nibabel as nib
        import numpy as np
        atlas = nib.load(self.inputs.in_atlas)
        data = atlas.get_fdata()
        roi_dir = Path(runtime.cwd) / "rois"
        roi_dir.mkdir(exist_ok=True)
        roi_list = []
        for idx in range(1, 247):
            mask = (data == idx).astype(np.uint8)
            if mask.sum() == 0:
                continue
            out_roi = roi_dir / f"roi_{idx}.nii.gz"
            nib.save(nib.Nifti1Image(mask, atlas.affine, atlas.header), out_roi)
            roi_list.append(out_roi)
        out_txt = runtime.cwd / "roi_list.txt"
        out_txt.write_text("\n".join(map(str, roi_list)))
        # Seed mask = sum of all masks
        seed_data = (data > 0).astype(np.uint8)
        seed_path = runtime.cwd / "seed_mask.nii.gz"
        nib.save(nib.Nifti1Image(seed_data, atlas.affine, atlas.header), seed_path)
        self._results["roi_list"] = str(out_txt)
        self._results["seed_mask"] = str(seed_path)
        return runtime
"""

roi_module = Path(__file__).with_suffix("_roi.py")
roi_module.write_text(make_roi_fn)

from importlib import import_module
MakeROI = import_module(roi_module.stem).MakeROI  # type: ignore

make_roi = Node(MakeROI(), name="make_roi")
WF.connect(flirt_atlas, "out_file", make_roi, "in_atlas")

################################################################################
# -------------------------  Bedpostx & Probtrackx2  ------------------------ #
################################################################################

if args.do_tract:
    bedpostx = Node(fsl.Bedpostx(ndirs=1, nvols=1, model=2), name="bedpostx")
    WF.connect(eddy, "out_corrected", bedpostx, "dwi")
    WF.connect(bet_b0, "mask_file", bedpostx, "mask")

    probtrackx = Node(fsl.ProbTrackX2(nsamples=args.nsamples, loopcheck=True), name="probtrackx")
    if args.matrix_mode == 1:
        probtrackx.inputs.network = True
    elif args.matrix_mode == 2:
        probtrackx.inputs.omatrix2 = True
    elif args.matrix_mode == 3:
        probtrackx.inputs.os2t = True
        probtrackx.inputs.omatrix1 = True
    elif args.matrix_mode == 4:
        probtrackx.inputs.omatrix3 = True
    WF.connect(bet_b0, "mask_file", probtrackx, "mask")
    WF.connect(bedpostx, "merged", probtrackx, "samples")
    WF.connect(make_roi, "roi_list", probtrackx, "seed")
    WF.connect(make_roi, "roi_list", probtrackx, "target_masks")

    # Convert DOT to CSV (Function interface)
    dot_csv = Node(
        niu.Function(input_names=["in_file", "out_file"], output_names=["csv_file"], function=dot_to_csv),
        name="dot_csv",
    )
    WF.connect(probtrackx, "out_matrix_file", dot_csv, "in_file")
    dot_csv.inputs.out_file = "connectivity_matrix.csv"

################################################################################
# ------------------------------  DataSink  ---------------------------------- #
################################################################################

datasink = Node(nio.DataSink(base_directory=str(out_root / "derivatives")), name="datasink")

WF.connect([
    (eddy, datasink, [("out_corrected", "preproc.@dwi")]),
    (dtifit, datasink, [("FA", "dti.@fa")]),
    (flirt_t1, datasink, [("out_file", "reg.@t1_dwi")]),
    (flirt_atlas, datasink, [("out_file", "reg.@atlas_dwi")]),
    (make_roi, datasink, [("roi_list", "rois.@list"), ("seed_mask", "rois.@seed")]),
])
if args.do_tract:
    WF.connect(dot_csv, datasink, [("csv_file", "tract.@connectome")])

################################################################################
# ------------------------------  Execute  ----------------------------------- #
################################################################################

if __name__ == "__main__":
    WF.run(plugin="MultiProc", plugin_args={"n_procs": args.n_procs})
    # Alternative: WF.run(plugin="SLURM", plugin_args={"sbatch_args": "--time=2:00:00"})
