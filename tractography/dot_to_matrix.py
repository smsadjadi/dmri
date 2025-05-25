import sys
import numpy as np

if len(sys.argv) != 3:
    print(f"Usage: {sys.argv[0]} <matrix.dot> <output.csv>")
    sys.exit(1)

inp = sys.argv[1]
out = sys.argv[2]

edges = []
max_idx = 0
with open(inp) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            i = int(parts[0])
            j = int(parts[1])
            v = float(parts[2])
        except ValueError:
            continue
        edges.append((i, j, v))
        max_idx = max(max_idx, i, j)

mat = np.zeros((max_idx, max_idx))
for i, j, v in edges:
    # probtrackx dot files are 1-indexed
    mat[i-1, j-1] = v

np.savetxt(out, mat, delimiter=',')

