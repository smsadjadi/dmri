import numpy as np
from dipy.align.imaffine import AffineRegistration, AffineMap
from dipy.align.transforms import RigidTransform3D


def motion_correction(dwi, affine, reference_volume=0):
    """Simple volume-to-volume motion correction using rigid-body registration."""
    n_vols = dwi.shape[-1]
    ref_data = dwi[..., reference_volume].astype(np.float32)
    corrected = []

    affreg = AffineRegistration(level_iters=[100, 50, 25],
                                sigmas=[3.0, 1.0, 0.0],
                                factors=[4, 2, 1])

    for idx in range(n_vols):
        moving = dwi[..., idx].astype(np.float32)
        rigid = affreg.optimize(ref_data, moving, RigidTransform3D(), None,
                                affine, affine)
        mapping = AffineMap(rigid.affine, moving.shape, affine,
                            ref_data.shape, affine)
        corrected.append(mapping.transform(moving))

    return np.stack(corrected, axis=-1)
