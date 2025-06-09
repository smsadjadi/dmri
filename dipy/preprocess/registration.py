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


def registration(
    moving_file,  # e.g., atlas or anatomical image
    fixed_file,   # e.g., preprocessed DWI or FA image
    out_dir="./output",
    out_name="registered.nii.gz",
):
    """
    Registers ``moving_file`` to the space of ``fixed_file`` using an affine
    transform and saves the resampled file.

    Parameters
    ----------
    moving_file : str
        Path to the image that needs to be transformed (e.g., WM mask in T1 space).
    fixed_file : str
        Path to the reference image in DWI space (e.g., b0 or FA).
    out_dir : str
        Directory to save the transformed file.
    out_name : str
        Filename for the transformed volume.

    Returns
    -------
    str
        Path to the transformed NIfTI file.
    """

    # 1. Load data
    moving_data, moving_affine = load_nifti(moving_file)
    fixed_data, fixed_affine = load_nifti(fixed_file)

    # 2. Setup registration
    affreg = AffineRegistration(
        metric=CCMetric(3),
        level_iters=[100, 50, 25],
        sigmas=[3.0, 1.0, 0.0],
        factors=[4, 2, 1]
    )

    # We do a multi-step registration: translation -> rigid -> affine
    transform = TranslationTransform3D()
    params0 = None
    translation = affreg.optimize(
        fixed_data, moving_data, transform,
        None, fixed_affine, moving_affine, starting_affine=params0
    )

    transform = RigidTransform3D()
    rigid = affreg.optimize(
        fixed_data, translation.transform(moving_data), transform,
        None, fixed_affine, moving_affine, starting_affine=translation.affine
    )

    transform = AffineTransform3D()
    affine_opt = affreg.optimize(
        fixed_data, rigid.transform(moving_data), transform,
        None, fixed_affine, moving_affine, starting_affine=rigid.affine
    )

    # 3. Apply the final transformation
    mapping = AffineMap(
        affine_opt.affine,
        moving_data.shape, moving_affine,
        fixed_data.shape, fixed_affine
    )
    transformed_data = mapping.transform(moving_data)

    # 4. Save output
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    save_nifti(out_path, transformed_data, fixed_affine)
    print(f"Saved coregistered file to: {out_path}")
    return out_path
