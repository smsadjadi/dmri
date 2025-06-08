#!/usr/bin/env bash

sig="-TERM"
[[ $1 == "--force" ]] && sig="-KILL"

script_name="tract.sh"
script_pattern=$(basename "$script_name")

echo ">>> Killing leftover $script_name/FSL jobs with SIG${sig#-} …"

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
    eddy_cuda eddy_openmp '^eddy diffusion' eddy_correct
    topup fugue flirt bet fslroi fslmaths fslsplit slicer
    bedpostx probtrackx2 dtifit
)

for pat in "${patterns[@]}"; do
    pkill $sig -f "$pat" 2>/dev/null
done

echo ">>> Done.  All residual pipeline processes have been signalled."
exit 0
