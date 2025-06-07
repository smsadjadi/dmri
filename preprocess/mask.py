import numpy as np
from dipy.segment.mask import median_otsu


def brain_mask(dwi, gtab):
    """Create a brain mask using median_otsu on the mean b0."""
    dwi_b0 = np.mean(dwi[..., gtab.b0s_mask], axis=-1)
    _, mask = median_otsu(dwi_b0, vol_idx=None, numpass=2, autocrop=False)
    return mask
