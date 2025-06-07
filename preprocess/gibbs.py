from dipy.denoise.gibbs import gibbs_removal


def remove_gibbs(dwi, slice_axis=2):
    """Remove Gibbs ringing artifacts from the DWI volume."""
    return gibbs_removal(dwi, slice_axis=slice_axis)
