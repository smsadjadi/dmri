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


def tensor_fit(preproc_dwi, preproc_affine, mask, gtab, out_dir="./output"):
    """
    Fit a DTI model to the preprocessed data and save FA (and other metrics).

    Parameters
    ----------
    preproc_dwi : np.ndarray
        Preprocessed DWI data (4D).
    preproc_affine : np.ndarray
        Affine of the preprocessed DWI.
    mask : np.ndarray
        Binary brain mask (3D).
    gtab : GradientTable
        DIPY gradient table.
    out_dir : str
        Output directory to save the tensor metrics.

    Returns
    -------
    fa : np.ndarray
        Fractional anisotropy volume.
    md : np.ndarray
        Mean diffusivity volume.
    """
    os.makedirs(out_dir, exist_ok=True)
    if mask is None:
        # If no explicit mask is given, just create a dummy full-volume mask
        mask = np.ones(preproc_dwi.shape[:3], dtype=bool)

    print("Fitting DTI model...")
    tensor_model = TensorModel(gtab)
    tensor_fit = tensor_model.fit(preproc_dwi, mask=mask)

    fa = tensor_fit.fa
    md = tensor_fit.md
    ad = tensor_fit.ad
    rd = tensor_fit.rd

    fa_file = os.path.join(out_dir, "fa.nii.gz")
    md_file = os.path.join(out_dir, "md.nii.gz")
    ad_file = os.path.join(out_dir, "ad.nii.gz")
    rd_file = os.path.join(out_dir, "rd.nii.gz")

    save_nifti(fa_file, fa, preproc_affine)
    save_nifti(md_file, md, preproc_affine)
    save_nifti(ad_file, ad, preproc_affine)
    save_nifti(rd_file, rd, preproc_affine)

    print(f"Saved DTI metrics: \nFA -> {fa_file} \nMD -> {md_file} \nAD -> {ad_file} \nRD -> {rd_file}")

    return fa, md, fa_file, md_file, ad_file, rd_file
