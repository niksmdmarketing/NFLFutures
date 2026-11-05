"""Published NBA/NHL award evaluations (research/NBA_NHL_AWARD_EVAL_RULE.md, 5 Nov 2026): attach `eval` like NFL awards_eval.
Display and Value-page gating only; never changes an award probability."""
import json
import os

from common import MODEL

PATH = os.path.join(MODEL, "award_eval_nba_nhl.json")


def attach(obj, sport):
    """obj = {"awards": {award: {...}}}; adds eval from model/award_eval_nba_nhl.json where present. Returns obj."""
    try:
        ev = json.load(open(PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return obj
    for award, item in (obj.get("awards") or {}).items():
        e = ev.get(f"{sport}:{award}")
        if e and isinstance(item, dict):
            item["eval"] = {k: e[k] for k in ("seasons", "log_loss", "baseline_log_loss", "mean_p_winner", "winner_in_pool",
                                              "fav_said", "fav_won", "fav_gap_ci90", "pass", "basis")}
            if not e.get("pass"):                     # a failed award never shows as beating its baseline
                item["eval"]["log_loss"] = max(e["log_loss"], e["baseline_log_loss"])
    return obj
