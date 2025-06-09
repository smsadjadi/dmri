import sys, csv, glob, os, numpy as np

src_dir, out_csv = sys.argv[1:]
mats = sorted(glob.glob(os.path.join(src_dir, "seed_*", "fdt_matrix1.dot")))
if not mats:
    sys.exit("No per-seed matrices found – nothing to merge.")

all_mats = [np.loadtxt(f) for f in mats]
conn2d   = np.sum(all_mats, axis=0)

with open(out_csv, "w", newline="") as f:
    csv.writer(f).writerows(conn2d)
print(f"Merged {len(mats)} matrices → {out_csv}")
