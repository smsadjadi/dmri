import os
from preprocess import preprocess, tensor_fit, registration
from tractography import deterministic_tractography, connectivity_from_streamlines


def run(subject_dir, atlas_path):
    os.makedirs(subject_dir, exist_ok=True)
    out_dir = os.path.join(subject_dir, "analyzed_dipy")
    os.makedirs(out_dir, exist_ok=True)

    dwi = os.path.join(subject_dir, "DTI-Mono_noPAT.nii.gz")
    bval = os.path.join(subject_dir, "DTI-Mono_noPAT.bval")
    bvec = os.path.join(subject_dir, "DTI-Mono_noPAT.bvec")

    preproc_dwi, affine, mask, gtab, dwi_file, mask_file = preprocess(
        dwi, bval, bvec,
        out_dir=out_dir,
        do_denoise=False,
        do_gibbs=True,
        do_motion_correction=True,
        do_masking=True,
    )

    tensor_fit(preproc_dwi, affine, mask, gtab, out_dir=out_dir)

    atlas_in_dwi = registration(
        atlas_path,
        dwi_file,
        out_dir=out_dir,
        out_name="atlas_in_dwi.nii.gz",
    )

    streamlines, trk_affine, _ = deterministic_tractography(
        dwi_file, mask_file, bval, bvec, out_dir
    )
    connectivity_from_streamlines(streamlines, atlas_in_dwi, trk_affine, out_dir)


if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    subject = os.path.join(SCRIPT_DIR, "dataset", "subj_01")
    atlas = os.path.join(SCRIPT_DIR, "atlases", "BN_Atlas_246_2mm.nii.gz")
    run(subject, atlas)