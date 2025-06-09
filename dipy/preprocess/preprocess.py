import os
import numpy as np
import nibabel as nib
from dipy.align.metrics import CCMetric
from dipy.denoise.localpca import mppca  # or nlmeans
from dipy.reconst.dti import TensorModel
from dipy.segment.mask import median_otsu
from dipy.align.imaffine import AffineMap
from dipy.denoise.gibbs import gibbs_removal
from dipy.core.gradients import gradient_table
from dipy.io.image import load_nifti, save_nifti
from dipy.align.imaffine import AffineRegistration
from dipy.align.transforms import TranslationTransform3D, RigidTransform3D, AffineTransform3D


def preprocess(
    dwi_file, bval_file, bvec_file, out_dir="./output",
    do_denoise=True, do_gibbs=True, do_motion_correction=True,
    do_masking=True,
    reference_volume=0
):
    """
    Preprocess a DWI dataset:
    1. Load data
    2. Denoise (optional)
    3. Gibbs artifact removal (optional)
    4. Motion correction (volume-to-volume registration) (optional)
    5. Masking (optional)
    6. Save preprocessed data + mask

    Parameters
    ----------
    dwi_file : str
        Path to the raw DWI NIfTI file.
    bval_file : str
        Path to the b-values text file.
    bvec_file : str
        Path to the b-vectors text file.
    out_dir : str
        Directory to save the outputs.
    do_denoise : bool
        If True, perform denoising using MPPCA.
    do_gibbs : bool
        If True, remove Gibbs ringing artifact.
    do_motion_correction : bool
        If True, perform volume-to-volume registration (motion correction).
    do_masking : bool
        If True, generate a brain mask using median_otsu.
    reference_volume : int
        Index of the volume used as reference for motion correction.

    Returns
    -------
    preproc_dwi : np.ndarray
        Preprocessed DWI data (4D).
    preproc_affine : np.ndarray
        Affine of the preprocessed DWI.
    mask : np.ndarray
        Binary mask (3D) of the brain (or None if do_masking=False).
    gtab : dipy.core.gradients.GradientTable
        Gradient table constructed from bvals/bvecs.
    """

    os.makedirs(out_dir, exist_ok=True)

    # 1. Load data
    dwi, affine = load_nifti(dwi_file)
    bvals = np.loadtxt(bval_file)
    bvecs = np.loadtxt(bvec_file).T  # sometimes bvecs are transposed
    gtab = gradient_table(bvals, bvecs)

    # 2. Denoise
    if do_denoise:
        print("Denoising data...")
        dwi = mppca(dwi, patch_shape=(5, 5, 5), returnsigma=False)

    # 3. Gibbs removal
    if do_gibbs:
        print("Removing Gibbs ringing artifacts...")
        dwi = gibbs_removal(dwi, slice_axis=2)

    # 4. Motion correction (volume-to-volume registration)
    if do_motion_correction:
        print("Performing volume-to-volume registration for motion correction...")
        n_vols = dwi.shape[-1]
        ref_data = dwi[..., reference_volume].astype(np.float32)
        corrected_volumes = []

        affreg = AffineRegistration(level_iters=[100, 50, 25],
                                    sigmas=[3.0, 1.0, 0.0],
                                    factors=[4, 2, 1])

        # Register each volume to the reference volume
        for vol_idx in range(n_vols):
            moving_data = dwi[..., vol_idx].astype(np.float32)

            # Perform rigid-body registration
            rigid_transform = RigidTransform3D()
            rigid = affreg.optimize(
                static=ref_data,
                moving=moving_data,
                transform=rigid_transform,
                params0=None,
                static_grid2world=affine,
                moving_grid2world=affine,
            )

            # Apply the rigid transform to the moving volume
            mapping = AffineMap(
                rigid.affine,
                moving_data.shape,
                affine,
                ref_data.shape,
                affine,
            )
            corrected_vol = mapping.transform(moving_data)
            corrected_volumes.append(corrected_vol)

        preproc_dwi = np.stack(corrected_volumes, axis=-1)
    else:
        preproc_dwi = dwi

    # 5. Brain masking
    if do_masking:
        print("Generating brain mask using median_otsu...")
        dwi_b0 = np.mean(preproc_dwi[..., gtab.b0s_mask], axis=3)
        masked_data, mask = median_otsu(dwi_b0, vol_idx=None, numpass=2, autocrop=False, dilate=1)
    else:
        mask = None

    # Save results
    preproc_dwi_file = os.path.join(out_dir, "dwi_preprocessed.nii.gz")
    save_nifti(preproc_dwi_file, preproc_dwi, affine)

    mask_file = None
    if mask is not None:
        mask_file = os.path.join(out_dir, "mask.nii.gz")
        save_nifti(mask_file, mask.astype(np.uint8), affine)
        print("Saved mask:", mask_file)

    print("Preprocessing done. Preprocessed DWI saved to:", preproc_dwi_file)
    return preproc_dwi, affine, mask, gtab, preproc_dwi_file, mask_file
