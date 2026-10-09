"""Append this run's forecasts to the forecast archive (a separate, append-only git branch).

    python pipeline/archive.py <archive_dir>

Writes <archive_dir>/<season>/<YYYYmmddTHHMMZ>.json.gz and appends a line to <archive_dir>/<season>/index.csv.
A snapshot is skipped when its probabilities are identical to the previous one (the simulation uses a fixed seed,
so numbers only change when the data changes). These files are the record used to score the frozen model later.
"""
import csv
import gzip
import hashlib
import json
import os
import sys

from common import OUT


def load(name):
    with open(os.path.join(OUT, name)) as f:
        return json.load(f)


def main(arch):
    meta, fut, aw = load("meta.json"), load("futures.json"), load("awards.json")
    teams = {t: {k: v[k] for k in ("rating", "mean_wins", "win_dist", "p_div", "p_playoff", "p_seed1", "p_conf", "p_sb",
                                   "seed_dist", "qb", "qb_adj", "press_adj") if k in v}
             for t, v in fut["teams"].items()}
    awards = {k: {"candidates": [[c["name"], c["team"], c["prob"]] for c in a.get("candidates", [])], "field": a.get("field")}
              for k, a in aw.items()}
    body = {"model": meta.get("model"), "season": meta["season"], "through_week": meta.get("through_week"),
            "next_week": meta.get("next_week"), "next_week_played": meta.get("next_week_played"),
            "injury_week": meta.get("injury_week"), "n_sims": meta.get("n_sims"), "teams": teams, "awards": awards}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]
    d = os.path.join(arch, str(meta["season"]))
    os.makedirs(d, exist_ok=True)
    idx = os.path.join(d, "index.csv")
    last = None
    if os.path.exists(idx):
        with open(idx) as f:
            rows = list(csv.DictReader(f))
            last = rows[-1]["hash"] if rows else None
    if digest == last:
        print("archive: unchanged since last snapshot, skipped")
        return
    stamp = meta["updated_utc"].replace("-", "").replace(":", "").replace("+0000", "Z").replace("+00", "Z")
    stamp = stamp[:13] + "Z" if not stamp.endswith("Z") else stamp
    name = f"{stamp}.json.gz"
    with gzip.open(os.path.join(d, name), "wt") as f:
        json.dump({"generated_utc": meta["updated_utc"], **body}, f, separators=(",", ":"))
    new = not os.path.exists(idx)
    with open(idx, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["file", "generated_utc", "model", "through_week", "next_week_played", "injury_week", "hash"])
        w.writerow([name, meta["updated_utc"], meta.get("model"), meta.get("through_week"), meta.get("next_week_played"),
                    meta.get("injury_week"), digest])
    print("archive: wrote", name)


if __name__ == "__main__":
    main(sys.argv[1])
