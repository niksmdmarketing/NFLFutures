"""Window-1 forecasts for research/NBA_PROPS_PRICE_TEST_RULE.md: replay the frozen live forecaster (research/nba_props_live.py, params
"b", season 2026 parameters) at 60 minutes before every 2025-26 regular-season tip-off from 1 Jan 2026, using only box scores of games
finished at least 3 hours earlier and official injury reports published by then (the forecaster's own offline replay mode).
One run per distinct cutoff time (all games sharing it are forecast together). Resumable: finished cutoffs are listed in done.txt.
Usage: python research/nba_props_window1.py <archive_dir> <reports_csv,reports_csv> [workers]
Note: the replay forecasts exactly at the cutoff; live forecasts are made 0-45 minutes before it, so window 1 sees up to 45 minutes
more news than a live forecast would. Stated as a limit in the rule's mechanics check."""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def cutoffs():
    s = pd.read_csv(os.path.join(ROOT, "data", "nba", "nba_schedule_2026.csv"), low_memory=False)
    s = s[pd.to_numeric(s.season_type, errors="coerce") == 2]
    tip = pd.to_datetime(s.game_date_time if "game_date_time" in s else s.date, utc=True, errors="coerce")
    lo, hi = os.environ.get("NBA_W1_FROM", "2026-01-01"), os.environ.get("NBA_W1_TO", "2026-05-01")   # Amendment 6 development replays
    tip = tip[(tip >= lo) & (tip < hi)].dropna()
    return sorted({(t - pd.Timedelta(minutes=60)) for t in tip})


def main(arch, reports, workers=2):
    done_p = os.path.join(arch, "done.txt")
    os.makedirs(arch, exist_ok=True)
    done = set(open(done_p).read().split()) if os.path.exists(done_p) else set()
    todo = [c for c in cutoffs() if c.isoformat() not in done]
    print("cutoffs to run:", len(todo), flush=True)
    env = dict(os.environ, NBA_PROPS_SEASON="2026", NBA_PROPS_PARAMS_ID="b", NBA_PROPS_REPLAY_REPORTS=reports)

    def one(c):
        r = subprocess.run([sys.executable, os.path.join(HERE, "nba_props_live.py"), arch, "--now", c.isoformat()], env=env,
                           capture_output=True, text=True, cwd=ROOT)
        ok = '"written"' in r.stdout and "error" not in r.stdout.splitlines()[-1][:200] if r.stdout else False
        with open(done_p, "a") as fh:
            if ok:
                fh.write(c.isoformat() + "\n")
        with open(os.path.join(arch, "window1_log.txt"), "a") as fh:
            fh.write(f"{c.isoformat()} ok={ok} {r.stdout.splitlines()[-1][:300] if r.stdout else r.stderr[-300:]}\n")
        return ok

    with ThreadPoolExecutor(workers) as ex:
        n_ok = sum(ex.map(one, todo))
    print("finished:", n_ok, "of", len(todo), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2)
