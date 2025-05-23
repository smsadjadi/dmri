import os
import yaml
import nibabel as nib

from tractography import connectivity

script_dir = os.path.dirname(os.path.abspath(__file__))
config_file_path = os.path.normpath(os.path.join(script_dir,'config','config.yml'))
with open(config_file_path, "r") as f: config = yaml.safe_load(f)
    
bval_file = config["data"]["bval_file"]
bvec_file = config["data"]["bvec_file"]
atlas_file = config["atlas"]["brainnetome"] # atlas aligned to DWI
output_dir = config["output_dir"]
dwi_preprocessed = f"{output_dir}/dwi_preprocessed.nii.gz"
mask_file = f"{output_dir}/mask.nii.gz"

dwi_file = "./output/dwi_preprocessed.nii.gz"
img = nib.load(dwi_file)
voxel_size = img.header.get_zooms()[:3]
print(f"Voxel size of preprocessed DWI: {voxel_size}")

connectivity, labels = connectivity(dwi_preprocessed, mask_file, atlas_file, bval_file, bvec_file, output_dir)
# connectivity, labels = connectivity_mni152(dwi_preprocessed, mask_file, atlas_file, bval_file, bvec_file, output_dir)

print("Adjacency matrix shape:", connectivity.shape)
print("Labels:", labels)