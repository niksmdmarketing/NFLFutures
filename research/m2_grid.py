"""M2 discovery grid (research/FUTURES_BAKEOFF_RULE.md Amendment 1). Usage: python m2_grid.py <outdir> [seasons first last]
Runs replay_afl.py for each m in {0.7,1.0,1.4}^3 on discovery seasons 2013-2018 and prints pooled playoff log loss (clip 0.001/0.999)."""
import itertools, os, subprocess, sys
import numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor
OUT = sys.argv[1]; FIRST, LAST = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (2013, 2018)
HERE = os.path.dirname(os.path.abspath(__file__))
GRID = [0.7, 1.0, 1.4]
def run(m):
    tag = "_".join(f"{x:.1f}" for x in m); d = os.path.join(OUT, tag); os.makedirs(d, exist_ok=True)
    if not all(os.path.exists(f"{d}/afl_{y}.csv") for y in range(FIRST, LAST + 1)):
        subprocess.run([sys.executable, f"{HERE}/replay_afl.py", str(FIRST), str(LAST)], check=True, capture_output=True,
                       env={**os.environ, "BT_OUTDIR": d, "BT_M": ",".join(map(str, m))})
    D = pd.concat([pd.read_csv(f"{d}/afl_{y}.csv") for y in range(FIRST, LAST + 1)])
    p = D.p_playoff.clip(0.001, 0.999); y = D.y_playoff
    return m, float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
if __name__ == "__main__":
    with ThreadPoolExecutor(max(1, os.cpu_count() or 1)) as ex:
        res = list(ex.map(run, itertools.product(GRID, repeat=3)))
    res.sort(key=lambda r: r[1])
    for m, ll in res: print(m, round(ll, 5), "<- live" if m == (1.0, 1.0, 1.0) else "")
