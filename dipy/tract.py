import os
import numpy as np
from dipy.io.image import load_nifti, save_nifti
from dipy.core.gradients import gradient_table
from preprocess import denoise, remove_gibbs, motion_correction, brain_mask, registration, tensor_fit
from tractography import deterministic_tractography, connectivity_from_streamlines


def run(subject_dir, atlas_path):
    """Run a simple DWI processing pipeline using DIPY."""
    out_dir = os.path.join(subject_dir, "analyzed_dipy")
    os.makedirs(out_dir, exist_ok=True)

    dwi_file = os.path.join(subject_dir, "DTI-Mono_noPAT.nii.gz")
    bval_file = os.path.join(subject_dir, "DTI-Mono_noPAT.bval")
    bvec_file = os.path.join(subject_dir, "DTI-Mono_noPAT.bvec")

    dwi, affine = load_nifti(dwi_file)
    bvals = np.loadtxt(bval_file)
    bvecs = np.loadtxt(bvec_file).T
    gtab = gradient_table(bvals, bvecs)

    print("Denoising ...")
    dwi = denoise(dwi)
    print("Removing Gibbs ringing ...")
    dwi = remove_gibbs(dwi)
    print("Motion correction ...")
    dwi = motion_correction(dwi, affine)
    print("Brain masking ...")
    mask = brain_mask(dwi, gtab)

    preproc_path = os.path.join(out_dir, "dwi_preprocessed.nii.gz")
    mask_path = os.path.join(out_dir, "mask.nii.gz")
    save_nifti(preproc_path, dwi, affine)
    save_nifti(mask_path, mask.astype(np.uint8), affine)

    print("Tensor fitting ...")
    tensor_fit(dwi, affine, mask, gtab, out_dir=out_dir)

    print("Registering atlas ...")
    atlas_in_dwi = registration(
        atlas_path,
        preproc_path,
        out_dir=out_dir,
        out_name="atlas_in_dwi.nii.gz",
    )

    print("Deterministic tractography ...")
    streamlines, trk_affine, _ = deterministic_tractography(preproc_path, mask_path, bval_file, bvec_file, out_dir)
    print("Computing connectivity matrix ...")
    connectivity_from_streamlines(streamlines, atlas_in_dwi, trk_affine, out_dir)


if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    subject = os.path.join(SCRIPT_DIR, "dataset", "subj_01")
    atlas = os.path.join(SCRIPT_DIR, "atlases", "BN_Atlas_246_2mm.nii.gz")
    run(subject, atlas)
