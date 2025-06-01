#!/usr/bin/env python3
import sys, os, numpy as np, csv

if len(sys.argv) != 3:
    sys.exit(f"Usage: {sys.argv[0]} <matrix.dot> <output.csv>")

dot_path, csv_path = sys.argv[1], sys.argv[2]

# ---------- first pass: find largest index ----------------------------------
max_idx = 0
with open(dot_path) as f:
    for ln in f:
        if ln.startswith('#') or not ln.strip():
            continue
        try:
            i, j, _ = ln.split()[:3]
            max_idx = max(max_idx, int(i), int(j))
        except ValueError:
            pass
size = max_idx                              # 1-indexed → 0-based later

# ---------- allocate on disk (float32 ≈ 4× smaller than float64) ------------
tmp_bin = csv_path + ".mmap"
mat = np.memmap(tmp_bin, dtype=np.float32, mode="w+", shape=(size, size))

# ---------- second pass: fill the matrix ------------------------------------
with open(dot_path) as f:
    for ln in f:
        if ln.startswith('#') or not ln.strip():
            continue
        try:
            i, j, v = ln.split()[:3]
            mat[int(i)-1, int(j)-1] = float(v)
        except ValueError:
            pass
mat.flush()

# ---------- stream out to CSV ----------------------------------------------
with open(csv_path, "w", newline="") as fout:
    writer = csv.writer(fout)
    for row in mat:
        writer.writerow(row)

# ---------- tidy up ---------------------------------------------------------
del mat
os.remove(tmp_bin)
