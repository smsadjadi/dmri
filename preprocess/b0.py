def extract_b0(dwi, index=0):
    """Return the b0 volume from a DWI dataset."""
    return dwi[..., index]
