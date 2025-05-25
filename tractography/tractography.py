import os
import numpy as np

from dipy.io.image import load_nifti
from dipy.core.gradients import gradient_table
from dipy.reconst.dti import TensorModel
from dipy.tracking.local_tracking import LocalTracking
from dipy.tracking.streamline import Streamlines
from dipy.tracking.stopping_criterion import BinaryStoppingCriterion
from dipy.tracking.utils import seeds_from_mask
from dipy.io.streamline import save_trk

from .connectivity import CustomTensorDirectionGetter, connectivity_from_streamlines


def deterministic_tractography(
    dwi_file,
    mask_file,
    bval_file,
    bvec_file,
    out_dir,
    step_size=0.5,
    fa_threshold=0.2,
):

    os.makedirs(out_dir, exist_ok=True)

    dwi, affine = load_nifti(dwi_file)
    # ensure writable, contiguous arrays to avoid cython buffer issues
    dwi = np.ascontiguousarray(dwi, dtype=np.float64)
    mask, _ = load_nifti(mask_file)
    mask = np.ascontiguousarray(mask).astype(bool)
    bvals = np.loadtxt(bval_file)
    bvecs = np.loadtxt(bvec_file).T
    gtab = gradient_table(bvals, bvecs)

    print("Fitting tensor model for tractography...")
    ten_model = TensorModel(gtab)
    ten_fit = ten_model.fit(dwi, mask=mask)
    fa = ten_fit.fa

    seeds = seeds_from_mask(mask, density=1, affine=affine)
    stopping_criterion = BinaryStoppingCriterion(fa > fa_threshold)
    principal_dirs = np.asarray(ten_fit.evecs[..., 0], dtype=np.float64)
    principal_dirs = np.ascontiguousarray(principal_dirs)
    direction_getter = CustomTensorDirectionGetter(principal_dirs, mask)

    streamlines_generator = LocalTracking(
        direction_getter,
        stopping_criterion,
        seeds,
        affine,
        step_size=step_size,
    )
    streamlines = Streamlines(streamlines_generator)

    tract_file = os.path.join(out_dir, "streamlines.trk")
    save_trk(tract_file, streamlines, affine, dwi.shape[:3])
    print(f"Streamlines saved to: {tract_file}")

    return streamlines, affine, tract_file


def tractography_connectivity(
    dwi_file,
    mask_file,
    atlas_file,
    bval_file,
    bvec_file,
    out_dir,
    step_size=0.5,
    fa_threshold=0.2,
):

    streamlines, affine, _ = deterministic_tractography(
        dwi_file,
        mask_file,
        bval_file,
        bvec_file,
        out_dir,
        step_size=step_size,
        fa_threshold=fa_threshold,
    )
    return connectivity_from_streamlines(streamlines, atlas_file, affine, out_dir)

