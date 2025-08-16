#!/bin/bash

sig="-TERM"
[[ $1 == "--force" ]] && sig="-KILL"

script_name="tract.sh"
script_pattern=$(basename "$script_name")

echo ">>> Killing leftover $script_name/FSL jobs with SIG${sig#-} …"

pgrep -f $script_name | while read -r tpid; do
    if [[ "$tpid" == "$$" ]]; then
        echo "  • Skipping self PID $tpid"
    else
        echo "  • Killing tract.sh PID $tpid"
        kill $sig "$tpid" 2>/dev/null
    fi
done

self_pgid=$(ps -o pgid= -p $$ | tr -d ' ')

ps -eo pid,pgid,cmd | grep -F "[${script_pattern:0:1}]${script_pattern:1}" | \
while read -r pid pgid _; do
    if [[ "$pgid" == "$self_pgid" ]]; then
        echo "  • (own PGID $pgid – skipping to avoid self-kill)"
    else
        echo "  • $script_name PID $pid  (PGID $pgid)"
        kill $sig -- -"$pgid" 2>/dev/null
    fi
done

pkill $sig -f "cpulimit .* $script_name" 2>/dev/null

patterns=(
  fslascii2img fsl2ascii fslcc fslchfiletype fslcomplex fslcpgeom fslcreatehd
  fsledithd fslfft fslhd fslinfo fslinterleave fslmaths fslmeants fslmerge
  fslnvols fslpspec fslroi fslslice fslsplit fslstats fslval fslreorient2std
  fslorient fslswapdim
  slicer slicesdir fsleyes fslview
  flirt mcflirt fnirt applywarp invwarp convertwarp convert_xfm applyxfm4D epi_reg
  prelude fugue fsl_prepare_fieldmap topup applytopup
  eddy eddy_openmp eddy_cuda eddy_correct eddy_quad eddy_squad
  dtifit bedpostx bedpostx_gpu xfibres probtrackx probtrackx2 probtrackx2_gpu
  feat feat_model film_gls fsl_glm melodic fsl_regfilt dual_regression
  fsl_motion_outliers randomise slicetimer susan
  bet bet2 fast run_first_all first_utils first_flirt fsl_anat siena sienax
  lesion_filling fslvbm tbss_1_preproc tbss_2_reg tbss_3_postreg tbss_4_prestats
  tbss_non_FA tbss_x swap_voxelwise swap_subjectwise
  oxford_asl asl_file
  fsl_sub fsl_sub_plugin_sge fsl_sub_plugin_slurm
)

for pat in "${patterns[@]}"; do
    pkill $sig -x "$pat" 2>/dev/null
done

echo ">>> Done.  All residual pipeline processes have been signalled."
exit 0
