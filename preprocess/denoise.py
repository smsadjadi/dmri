import numpy as np
from dipy.denoise.localpca import mppca


def denoise(dwi):
    """Denoise diffusion data using MPPCA."""
    dwi = np.asarray(dwi)
    return mppca(dwi, patch_shape=(5, 5, 5), returnsigma=False)
