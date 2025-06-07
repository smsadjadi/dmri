#!/bin/bash
# set -e

# -------- USER CONFIG --------
: "${DO_TRACT:=1}"        # 1 = run tractography, 0 = skip completely
: "${MATRIX_MODE:=1}"     # 1 = ROI×ROI, 2 = ROI×voxel, 3 = voxel×ROI, 4 = voxel×voxel
: "${NSAMPLES:=5000}"     # fewer samples → much smaller .dot files

# -------- DIRECTORIES --------
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dataset="$script_dir/dataset"
pyenv="$HOME/pyenv/nienv/bin/python"

# -------- CLEAN-UP PIDs --------
for pid in $(pgrep -f "$(basename "$0")"); do
    [[ "$pid" != "$$" ]] && {
        echo "Stopping previous instance → PID $pid"
        kill -9 "$pid" 2>/dev/null
    }
done

# -------- EXECUSION --------
if [[ "$LIMITED" != "1" ]]; then
    {
      echo
      echo "========================================="
      echo "New FSL run started @ $(date '+%Y-%m-%d %H:%M:%S')"
      echo "========================================="
      echo "launching under 50% cpulimit..."
    } >> $dataset/fsl.log 2>&1
    CORES=$(nproc)
    CPU_LIMIT=$((CORES * 50))
    LIMITED=1 exec cpulimit -l $CPU_LIMIT -- "$0" "$@" >> $dataset/fsl.log 2>&1
fi

# -------- DATASET --------
subjects=("subj_01" "subj_02" "subj_03" "subj_04" "subj_05" "subj_06" "subj_07" "subj_08" "subj_09" "subj_10")
if [ ${#subjects[@]} -eq 0 ]; then
    mapfile -t subjects < <(ls -1 "$dataset")
fi
for subject in "${subjects[@]}"; do
echo "👨🏻‍💻 <<< ${subject}"

# -------- DATA LOADER --------
datadir="$dataset/$subject"
outdir="$datadir/analyzed_fsl"
mkdir -p "$outdir"

# -------- CONFIGURATION --------
dwi="$datadir/DTI-Mono_noPAT.nii.gz"
dwi_json="$datadir/DTI-Mono_noPAT.json"
bval="$datadir/DTI-Mono_noPAT.bval"
bvec="$datadir/DTI-Mono_noPAT.bvec"
topup_ap="$datadir/ap_b0.nii.gz"
topup_pa="$datadir/pa_b0.nii.gz"
mag="$datadir/gre_field_mapping_2mm_e1.nii.gz"
phase="$datadir/gre_field_mapping_2mm_e2.nii.gz"
t1="$datadir/t1_mprage_tra.nii.gz"
atlas="$script_dir/atlases/BN_Atlas_246_2mm.nii.gz"
roi_list="$outdir/roi_list.txt"
seed_mask="$outdir/seed_mask.nii.gz"

# -------- Copy DWI --------
echo "-------------------------------------"
if [[ ! -f "$outdir/dwi.nii.gz" ]]; then
    echo "Copying DWI..."
    cp "$dwi" "$outdir/dwi.nii.gz"
    fslcpgeom "$dwi" "$outdir/dwi.nii.gz"
    cp "$bval" "$outdir/bvals"
    cp "$bvec" "$outdir/bvecs"
else
echo "✔️ Copy DWI"
fi

# -------- Fieldmap Preparation --------
echo "-------------------------------------"
if [[ ! -f "$outdir/fieldmap_rads.nii.gz" ]]; then
    echo "Preparing fieldmap from GRE..."
    te_diff=2.46
    fsl_prepare_fieldmap SIEMENS "$phase" "$mag" "$outdir/fieldmap_rads.nii.gz" "$te_diff" --nocheck || {
        echo "Fieldmap preparation failed, continuing without distortion correction"
        touch "$outdir/fieldmap_failed"
    }
else
echo "✔️ Fieldmap Preparation"
fi

# ---------- B0 Creation ----------
echo "-------------------------------------"
if [[ ! -f "$outdir/b0" ]]; then
    echo "Creating B0..."
    fslroi "$outdir/dwi.nii.gz" "$outdir/b0" 0 1
    bet     "$outdir/b0" "$outdir/b0_brain" -f 0.3 -m
else
echo "✔️ B0 Creation"
fi

# -------- Fieldmap Alignment to DWI --------
echo "-------------------------------------"
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
echo "✔️ Fieldmap Alignment to DWI"
fi

# -------- EPI Distortion Correction --------
echo "-------------------------------------"
if [[ ! -f "$outdir/dwi_unwarped.nii.gz" ]]; then
    echo "Applying EPI distortion correction with fugue..."
    dwell=$(jq -r '."EffectiveEchoSpacing" // empty' "$dwi_json")
    if [[ -n "$fieldmap" ]]; then
        fugue -i "$outdir/dwi.nii.gz" --loadfmap="$fieldmap" \
              --unwarpdir=z --dwell=${dwell} \
              --mask="$outdir/b0_brain_mask.nii.gz" \
              -u "$outdir/dwi_unwarped.nii.gz" || {
            echo "FUGUE failed, using original DWI volume"
            cp "$outdir/dwi.nii.gz" "$outdir/dwi_unwarped.nii.gz"
        }
    else
        echo "Fieldmap not available, skipping distortion correction"
        cp "$outdir/dwi.nii.gz" "$outdir/dwi_unwarped.nii.gz"
    fi
else
echo "✔️ EPI Distortion Correction"
fi

# -------- Eddy Correction --------
echo "-------------------------------------"
if [[ -f "$topup_ap" && -f "$topup_pa" && ! -f "$outdir/dwi_eddy.nii.gz" ]]; then
    echo "Eddy and motion correction..."
    mkdir -p $outdir/eddy
    # Prepare topup (only if needed)
    if [ ! -f "$outdir/topup_fieldmap.nii.gz" ]; then
        fslmerge -t $outdir/topup_b0s $topup_ap $topup_pa
        echo "0 -1 0 0.05" > $outdir/acqparams.txt
        echo "0 1 0 0.05" >> $outdir/acqparams.txt
        topup --imain=$outdir/topup_b0s --datain=$outdir/acqparams.txt \
              --config=b02b0.cnf --out=$outdir/topup_results \
              --iout=$outdir/topup_corrected_b0 --fout=$outdir/topup_fieldmap
    fi
    # Prepare index and mask
    nvols=$(fslnvols $dwi)
    indx=""
    for ((i=1; i<=${nvols}; i+=1)); do indx="$indx 1"; done
    echo $indx > $outdir/index.txt
    bet $topup_ap $outdir/nodif_brain -m -f 0.2
    eddy_openmp --imain=${dwl} \
                --mask=$outdir/nodif_brain_mask \
                --acqp=$outdir/acqparams.txt \
                --index=$outdir/index.txt \
                --bvecs=${bvec} --bvals=${bval} \
                --topup=$outdir/topup_results \
                --out=$outdir/dwi_eddy
elif [[ ! -f "$outdir/dwi_eddy.nii.gz" ]]; then
    echo "Running eddy correction..."
    fslroi "$outdir/dwi_unwarped.nii.gz" "$outdir/nodif" 0 1
    bet "$outdir/nodif" "$outdir/nodif_brain" -f 0.3 -m
    eddy_correct "$outdir/dwi_unwarped.nii.gz" "$outdir/dwi_eddy.nii.gz" 0
else
echo "✔️ Eddy Correction"
fi

# -------- Eddy Quality Control --------
echo "-------------------------------------"
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
else
echo "✔️ Eddy Quality Control"
fi

# -------- Brain Mask --------
echo "-------------------------------------"
if [[ ! -f "$outdir/brain_mask.nii.gz" ]]; then
    echo "Creating brain mask..."
    # fslmaths $outdir/dwi_eddy.nii.gz -Tmean $outdir/dwi_mean
    fslroi "$outdir/dwi_eddy.nii.gz" "$outdir/nodif_posteddy" 0 1
    bet "$outdir/nodif_posteddy" "$outdir/nodif_brain_posteddy" -f 0.3 -m
    cp "$outdir/nodif_brain_posteddy_mask.nii.gz" "$outdir/brain_mask.nii.gz"
else
echo "✔️ Brain Mask"
fi

# -------- Tensor Fit --------
echo "-------------------------------------"
if [[ ! -f "$outdir/dti_FA.nii.gz" ]]; then
    echo "Fitting DTI model..."
    dtifit -k "$outdir/dwi_eddy.nii.gz" \
           -o "$outdir/dti" \
           -m "$outdir/brain_mask.nii.gz" \
           -r "$outdir/bvecs" \
           -b "$outdir/bvals"
else
echo "✔️ Tensor Fit"
fi

# -------- T1 to DWI Register --------
echo "-------------------------------------"
if [[ ! -f "$outdir/t1_in_dwi.nii.gz" ]]; then
    echo "Registering T1 to DWI..."
    flirt -in "$t1" -ref "$outdir/nodif_posteddy" \
          -out "$outdir/t1_in_dwi.nii.gz" -omat "$outdir/t1_to_dwi.mat" -dof 6
else
echo "✔️ T1 to DWI Register"
fi

# -------- Atlas to DWI Register --------
echo "-------------------------------------"
if [[ ! -f "$outdir/atlas_in_dwi.nii.gz" ]]; then
    echo "Registering MNI-space atlas directly to DWI space..."
    flirt -in "$atlas" -ref "$outdir/nodif_posteddy.nii.gz" \
          -out "$outdir/atlas_in_dwi.nii.gz" \
          -applyxfm -usesqform
else
echo "✔️ Atlas to DWI Register"
fi

# -------- Binary ROI Masks & List --------
echo "-------------------------------------"
if [[ ! -f "$roi_list" ]]; then
    echo "Creating binary ROI masks from atlas..."
    mkdir -p "$outdir/rois"
    rm -f "$roi_list"
    for idx in $(seq 1 246); do
        roi="$outdir/rois/roi_${idx}.nii.gz"
        # binarise label idx
        fslmaths "$outdir/atlas_in_dwi.nii.gz" -thr ${idx} -uthr ${idx} -bin "$roi"
        # keep only non-empty masks (in case some labels are outside FOV)
        if [[ $(fslstats "$roi" -V | awk '{print $1}') -gt 0 ]]; then
            echo "$roi" >> "$roi_list"
        else
            rm -f "$roi"
        fi
    done
else
echo "✔️ Binary ROI Masks & List"
fi

# -------- Seed Mask Creation --------
echo "-------------------------------------"
if [[ ! -f "$seed_mask" ]]; then
    echo "Creating combined seed mask from all ROIs..."
    fslmaths "$(head -n 1 "$roi_list")" -mul 0 "$seed_mask"  # init empty image
    while IFS= read -r roi; do
        fslmaths "$seed_mask" -add "$roi" "$seed_mask"
    done < "$roi_list"
    fslmaths "$seed_mask" -bin "$seed_mask"
else
    echo "✔️ Seed Mask Creation"
fi

# -------- Probabilistic Tractography & Connectivity --------
echo "-------------------------------------"
if [[ "$MATRIX_MODE" -eq 1 ]]; then out_mat="$outdir/probtrackx/fdt_network_matrix"
else out_mat="$outdir/probtrackx/fdt_matrix${MATRIX_MODE}.dot"; fi
if [[ "$DO_TRACT" -eq 1 ]]; then
  if [[ ! -f "$out_mat" ]]; then
    echo "Running bedpostx for diffusion modelling..."
    if [[ ! -d "$outdir.bedpostX" ]]; then
        ln -sf "$outdir/dwi_eddy.nii.gz"       "$outdir/data.nii.gz"
        ln -sf "$outdir/brain_mask.nii.gz"     "$outdir/nodif_brain_mask.nii.gz"
        bedpostx "$outdir" || { echo "bedpostx failed"; exit 1; }
    fi
    echo "Running probtrackx2 (matrix mode $MATRIX_MODE)…"
    mkdir -p "$outdir/probtrackx"
    case "$MATRIX_MODE" in
        1) prob_opts="--network --seed=$roi_list --targetmasks=$roi_list" ;;  # ROI-to-ROI matrix
        2) prob_opts="--omatrix2 --seed=$roi_list" ;; # ROI seed to voxel targets
        3) prob_opts="--os2t --omatrix1 --seed=$seed_mask --targetmasks=$roi_list" ;; # Voxel seeds to ROI targets
        4) prob_opts="--omatrix3 --seed=$seed_mask" ;; # Full voxel-to-voxel matrix
        *) echo "❌ Invalid MATRIX_MODE ($MATRIX_MODE)"; exit 1 ;;
    esac
    probtrackx2 \
        --samples="$outdir.bedpostX/merged" \
        --mask="$outdir/nodif_brain_mask.nii.gz" \
        --loopcheck --forcedir \
        --nsamples="$NSAMPLES" \
        $prob_opts \
        --dir="$outdir/probtrackx"
  else
    echo "✔️ Probabilistic Tractography & Connectivity"
  fi
else
  echo "⚠️ DO_TRACT=0 → Skipping edpostx/probtrackx"
fi

# -------- Dot to CSV --------
echo "-------------------------------------"
if [[ ! -f "$outdir/connectivity_matrix.csv" && -f "$out_mat" && "$out_mat" == *.dot ]]; then
    echo "Converting Dot matrix to CSV..."
    $pyenv "$script_dir/tractography/dot_to_matrix.py" \
            "$out_mat" "$outdir/connectivity_matrix.csv"
    echo "✔️ Connectivity matrix saved: $outdir/connectivity_matrix.csv"
else
echo "✔️ Dot to CSV"
fi

# -------- Quality Control --------
echo "-------------------------------------"
if [[ ! -f "$outdir/qc_fa_slices.png" ]]; then
    echo "Generating QC slices for FA..."
    slicer "$outdir/dti_FA.nii.gz" -a "$outdir/qc_fa_slices.png"
else
echo "✔️ Quality Control"
fi

# -------- Done --------
echo "========================================="
echo "✅ FSL pipeline complete @ $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================="
done

# -------- Kill PID --------
kill -9 "$$" 2>/dev/null