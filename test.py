import os
import sys
import numpy as np
import nibabel as nib
from tempfile import TemporaryDirectory

from dipy.tracking.streamline import Streamlines
from preprocess import preprocess, tensor_fit
from tractography import deterministic_tractography, connectivity_from_streamlines


def create_dummy_dwi(tmpdir, shape=(3,3,3,4)):
    data = np.random.rand(*shape)
    affine = np.eye(4)
    dwi_path = os.path.join(tmpdir, 'dwi.nii.gz')
    nib.save(nib.Nifti1Image(data, affine), dwi_path)
    bvals = np.array([0, 1000, 1000, 1000])
    bvecs = np.eye(3)
    bvecs = np.vstack(([[0,0,0]], bvecs))[:4]  # ensure 4x3
    bval_path = os.path.join(tmpdir, 'bvals')
    bvec_path = os.path.join(tmpdir, 'bvecs')
    np.savetxt(bval_path, bvals)
    np.savetxt(bvec_path, bvecs)
    mask = np.ones(shape[:3], dtype=np.uint8)
    mask_path = os.path.join(tmpdir, 'mask.nii.gz')
    nib.save(nib.Nifti1Image(mask, affine), mask_path)
    return dwi_path, bval_path, bvec_path, mask_path, affine


def test_preprocess_and_tensor_fit():
    with TemporaryDirectory() as tmpdir:
        dwi, bval, bvec, _, _ = create_dummy_dwi(tmpdir)
        preproc_dwi, aff, mask, gtab, dwi_file, mask_file = preprocess(
            dwi,
            bval,
            bvec,
            out_dir=tmpdir,
            do_denoise=False,
            do_gibbs=False,
            do_motion_correction=False,
            do_masking=True,
        )
        fa, md, fa_file, md_file, *_ = tensor_fit(preproc_dwi, aff, mask, gtab, out_dir=tmpdir)
        assert os.path.exists(fa_file)
        assert fa.shape == mask.shape


def test_connectivity_from_streamlines_only():
    with TemporaryDirectory() as tmpdir:
        affine = np.eye(4)
        streamlines = Streamlines(
            [
                np.array([[0, 0, 0], [2, 0, 0]], dtype=float),
                np.array([[2, 2, 2], [0, 2, 2]], dtype=float),
            ]
        )

        atlas = np.zeros((3, 3, 3), dtype=np.int16)
        atlas[0, :, :] = 1
        atlas[2, :, :] = 2
        atlas_path = os.path.join(tmpdir, "atlas.nii.gz")
        nib.save(nib.Nifti1Image(atlas, affine), atlas_path)

        conn, labels = connectivity_from_streamlines(streamlines, atlas_path, affine, tmpdir)
        assert conn.shape[0] == 3
        assert len(labels) == 3  # includes background
