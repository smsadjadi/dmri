#!/bin/bash
set -e

# -------- DIRECTORIES ---------
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dataset="$script_dir/dataset"

# List of subjects to process. If left empty all directories inside the
# dataset folder are processed.
subjects=("subj_01")
if [ ${#subjects[@]} -eq 0 ]; then
    mapfile -t subjects < <(ls -1 "$dataset")
fi
for subject in "${subjects[@]}"; do

# -------- DATA LOADER ---------
datadir="$dataset/$subject"
outdir="$datadir/preprocessed"
mkdir -p "$outdir"

# -------- CONFIGURATION --------
dwi="$datadir/DTI-Mono_noPAT.nii.gz"
bval="$datadir/DTI-Mono_noPAT.bval"
bvec="$datadir/DTI-Mono_noPAT.bvec"
topup_ap="$datadir/ap_b0.nii.gz"
topup_pa="$datadir/pa_b0.nii.gz"
mag="$datadir/gre_field_mapping_2mm_e1.nii.gz"
phase="$datadir/gre_field_mapping_2mm_e2.nii.gz"
t1="$datadir/t1_mprage_tra.nii.gz"
atlas="$script_dir/atlases/BN_Atlas_246_2mm.nii.gz"

# -------- STEP 1: Copy DWI --------
if [[ ! -f "$outdir/dwi.nii.gz" ]]; then
    echo "Copying DWI..."
    cp "$dwi" "$outdir/dwi.nii.gz"
    fslcpgeom "$dwi" "$outdir/dwi.nii.gz"
    cp "$bval" "$outdir/bvals"
    cp "$bvec" "$outdir/bvecs"
fi

# -------- STEP 2: Fieldmap preparation --------
if [[ ! -f "$outdir/fieldmap_rads.nii.gz" ]]; then
    echo "Preparing fieldmap from GRE..."
    te_diff=2.46
    fsl_prepare_fieldmap SIEMENS "$phase" "$mag" "$outdir/fieldmap_rads.nii.gz" "$te_diff" --nocheck || {
        echo "Fieldmap preparation failed, continuing without distortion correction"
        touch "$outdir/fieldmap_failed"
    }
fi

# Align fieldmap to DWI space if dimensions do not match
if [[ -f "$outdir/fieldmap_rads.nii.gz" ]]; then
    dwi_dim=$(fslhd "$outdir/dwi.nii.gz" | awk '/^dim1/ {d1=$2} /^dim2/ {d2=$2} /^dim3/ {d3=$2} END{print d1"x"d2"x"d3}')
    fmap_dim=$(fslhd "$outdir/fieldmap_rads.nii.gz" | awk '/^dim1/ {d1=$2} /^dim2/ {d2=$2} /^dim3/ {d3=$2} END{print d1"x"d2"x"d3}')
    if [[ "$dwi_dim" != "$fmap_dim" ]]; then
        echo "Resampling fieldmap to match DWI dimensions..."
        flirt -in "$outdir/fieldmap_rads.nii.gz" -ref "$outdir/b0" \
              -applyxfm -usesqform -out "$outdir/fieldmap_rads_resamp.nii.gz"
        fieldmap="$outdir/fieldmap_rads_resamp.nii.gz"
    else
        fieldmap="$outdir/fieldmap_rads.nii.gz"
    fi
else
    fieldmap=""
fi

# -------- STEP 3: EPI distortion correction --------
if [[ ! -f "$outdir/dwi_unwarped.nii.gz" ]]; then
    echo "Applying EPI distortion correction with fugue..."
    fslroi "$outdir/dwi.nii.gz" "$outdir/b0" 0 1
    bet "$outdir/b0" "$outdir/b0_brain" -f 0.3 -m
    if [[ -n "$fieldmap" ]]; then
        fugue -i "$outdir/dwi.nii.gz" --loadfmap="$fieldmap" \
              --unwarpdir=z -u "$outdir/dwi_unwarped.nii.gz" \
              --mask="$outdir/b0_brain_mask.nii.gz" || {
            echo "FUGUE failed, using original DWI volume"
            cp "$outdir/dwi.nii.gz" "$outdir/dwi_unwarped.nii.gz"
        }
    else
        echo "Fieldmap not available, skipping distortion correction"
        cp "$outdir/dwi.nii.gz" "$outdir/dwi_unwarped.nii.gz"
    fi
fi

# -------- STEP 4: Eddy correction (motion + eddy) --------
if [[ ! -f "$outdir/dwi_eddy.nii.gz" ]]; then
    echo "Running eddy correction..."
    fslroi "$outdir/dwi_unwarped.nii.gz" "$outdir/nodif" 0 1
    bet "$outdir/nodif" "$outdir/nodif_brain" -f 0.3 -m
    eddy_correct "$outdir/dwi_unwarped.nii.gz" "$outdir/dwi_eddy.nii.gz" 0
fi

# # -------- STEP 4: Eddy correction (with topup) --------
# if [ ! -f "$outdir/dwi_eddy.nii.gz" ]; then
#     echo "Step 1: Eddy and motion correction"
#     mkdir -p $outdir/eddy
#     # Prepare topup (only if needed)
#     if [ ! -f "$outdir/topup_fieldmap.nii.gz" ]; then
#         fslmerge -t $outdir/topup_b0s $topup_ap $topup_pa
#         echo "0 -1 0 0.05" > $outdir/acqparams.txt
#         echo "0 1 0 0.05" >> $outdir/acqparams.txt
#         topup --imain=$outdir/topup_b0s --datain=$outdir/acqparams.txt \
#               --config=b02b0.cnf --out=$outdir/topup_results \
#               --iout=$outdir/topup_corrected_b0 --fout=$outdir/topup_fieldmap
#     fi
#     # Prepare index and mask
#     nvols=$(fslnvols $DWI)
#     indx=""
#     for ((i=1; i<=${nvols}; i+=1)); do indx="$indx 1"; done
#     echo $indx > $outdir/index.txt
#     bet $topup_ap $outdir/nodif_brain -m -f 0.2
#     eddy_openmp --imain=${DWI} \
#                 --mask=$outdir/nodif_brain_mask \
#                 --acqp=$outdir/acqparams.txt \
#                 --index=$outdir/index.txt \
#                 --bvecs=${BVEC} --bvals=${BVAL} \
#                 --topup=$outdir/topup_results \
#                 --out=$outdir/dwi_eddy
# fi

# -------- Step 4.5: Eddy Quality Control --------
if [ ! -d "$outdir/eddy_qc" ]; then
    if [[ -f "$outdir/index.txt" && -f "$outdir/acqparams.txt" ]]; then
        echo "Eddy quality control..."
        mkdir -p "$outdir/eddy_qc"
        eddy_quad "$outdir/dwi_eddy" \
            -idx "$outdir/index.txt" \
            -par "$outdir/acqparams.txt" \
            -m "$outdir/nodif_brain_mask" \
            -b "$bval" \
            -g "$bvec" \
            -o "$outdir/eddy_qc"
        echo "Eddy QC report created at $outdir/eddy_qc"
    else
        echo "Skipping eddy_quad QC (index/acqparams not found)"
    fi
fi

# -------- STEP 5: Brain mask --------
if [[ ! -f "$outdir/brain_mask.nii.gz" ]]; then
    echo "Creating brain mask..."
    # fslmaths $outdir/dwi_eddy.nii.gz -Tmean $outdir/dwi_mean
    fslroi "$outdir/dwi_eddy.nii.gz" "$outdir/nodif_posteddy" 0 1
    bet "$outdir/nodif_posteddy" "$outdir/nodif_brain_posteddy" -f 0.3 -m
    cp "$outdir/nodif_brain_posteddy_mask.nii.gz" "$outdir/brain_mask.nii.gz"
fi

# -------- STEP 6: Tensor fitting --------
if [[ ! -f "$outdir/dti_FA.nii.gz" ]]; then
    echo "Fitting DTI model..."
    dtifit -k "$outdir/dwi_eddy.nii.gz" \
           -o "$outdir/dti" \
           -m "$outdir/brain_mask.nii.gz" \
           -r "$outdir/bvecs" \
           -b "$outdir/bvals"
fi

# -------- STEP 7: Register T1 to DWI --------
if [[ ! -f "$outdir/t1_in_dwi.nii.gz" ]]; then
    echo "Registering T1 to DWI..."
    flirt -in "$t1" -ref "$outdir/nodif_posteddy" \
          -out "$outdir/t1_in_dwi.nii.gz" -omat "$outdir/t1_to_dwi.mat" -dof 6
fi

# -------- STEP 8: Register MNI Atlas to DWI --------
if [[ ! -f "$outdir/atlas_in_dwi.nii.gz" ]]; then
    echo "Registering MNI-space atlas directly to DWI space..."
    flirt -in "$atlas" \
          -ref "$outdir/nodif_posteddy.nii.gz" \
          -out "$outdir/atlas_in_dwi.nii.gz" \
          -applyxfm -usesqform
    echo "Atlas registered to DWI space: $outdir/atlas_in_dwi.nii.gz"
fi

# -------- STEP 9: Probabilistic Tractography & Connectivity Matrix --------
if [[ ! -f "$outdir/connectivity_matrix.csv" ]]; then
    echo "Running bedpostx for diffusion modeling..."
    if [[ ! -d "$outdir.bedpostX" ]]; then
        ln -sf "$outdir/dwi_eddy.nii.gz" "$outdir/data.nii.gz"
        ln -sf "$outdir/brain_mask.nii.gz" "$outdir/nodif_brain_mask.nii.gz"
        bedpostx "$outdir" || {
            echo "bedpostx failed - skipping tractography.";
        }
    fi
    if [[ -d "$outdir.bedpostX" && -f "$outdir.bedpostX/merged" ]]; then
        echo "Running probtrackx2 for tractography..."
        mkdir -p "$outdir/probtrackx"
        probtrackx2 --samples="$outdir.bedpostX/merged" \
                    --mask="$outdir/nodif_brain_mask.nii.gz" \
                    --seed="$outdir/atlas_in_dwi.nii.gz" \
                    --loopcheck --forcedir --opd \
                    --dir="$outdir/probtrackx" \
                    --targetmasks="$outdir/atlas_in_dwi.nii.gz" \
                    --os2t --omatrix1

        cp "$outdir/probtrackx/fdt_matrix1.dot" "$outdir/connectivity_matrix.csv"
        echo "Connectivity matrix saved: $outdir/connectivity_matrix.csv"
    else
        echo "Skipping probtrackx2 - bedpostx output not found.";
    fi
    echo "Running probtrackx2 for tractography..."
    mkdir -p "$outdir/probtrackx"
    probtrackx2 --samples="$outdir.bedpostX/merged" \
                --mask="$outdir/nodif_brain_mask.nii.gz" \
                --seed="$outdir/atlas_in_dwi.nii.gz" \
                --loopcheck --forcedir --opd \
                --dir="$outdir/probtrackx" \
                --targetmasks="$outdir/atlas_in_dwi.nii.gz" \
                --os2t --omatrix1

    cp "$outdir/probtrackx/fdt_matrix1.dot" "$outdir/fdt_matrix1.dot"
    echo "Converting tractography output to connectivity matrix..."
    python3 "$script_dir/tractography/dot_to_matrix.py" \
        "$outdir/fdt_matrix1.dot" "$outdir/connectivity_matrix.csv"
    rm "$outdir/fdt_matrix1.dot"
    echo "Connectivity matrix saved: $outdir/connectivity_matrix.csv"
fi

# -------- STEP 10: Quality Control --------
if [[ ! -f "$outdir/qc_fa_slices.png" ]]; then
    echo "Generating QC slices for FA..."
    slicer "$outdir/dti_FA.nii.gz" -a "$outdir/qc_fa_slices.png"
fi

# -------- (Optional) Tractography & Connectome --------
echo "Next steps (Optional):"
echo "  - Use MRtrix or DIPY for deterministic tractography or more advanced options."
echo "  - Perform atlas registration & generate connectivity matrices."
echo "✅ FSL Pipeline complete."

done
echo "All subjects processed."
