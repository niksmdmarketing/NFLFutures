"""Interim descriptive scoring; never makes an adoption/profitability decision.

Uses the archive audit's selected 60-minute forecasts and completed ESPN boxes.
Missing players are unknown, NOT inferred DNPs. DNPs get an appearance score,
not a zero-valued conditional prop or a hypothetical losing bet.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import urllib.request

from nba_props_archive_audit import GitArchive
from nba_teams import resolve


def minutes_value(value):
    if ":" in str(value):
        minute, second = str(value).split(":")
        return float(minute) + float(second) / 60
    return float(value)


def box_complete(actual, team):
    """A team's final box is treated as complete only when its appearing players' minutes add to 240 + 25 x overtimes (within 2)
    and at least five players appeared. Otherwise a missing candidate stays unknown (GPT, 22 Oct 2026)."""
    if actual.get(("__score_ok__", team), {}).get("ok") is False or ("__score_ok__", team) not in actual:
        return False
    mins = [v["minutes"] for (t, _), v in actual.items() if t == team and v["appeared"]]
    total = sum(mins)
    if len(mins) < 5 or total < 238:
        return False
    return abs((total - 240) - 25 * round((total - 240) / 25)) <= 2


def box_players(document, game_id=None):
    comp = document.get("header", {}).get("competitions", [{}])[0]
    if not comp.get("status", {}).get("type", {}).get("completed"):
        raise ValueError("game_not_final")
    if game_id is not None and str(comp.get("id", game_id)) != str(game_id):
        raise ValueError("game_id_mismatch")
    final = {resolve(c["team"]["abbreviation"]): int(c["score"]) for c in comp.get("competitors", []) if c.get("score") not in (None, "")}
    out = {}
    for team in document.get("boxscore", {}).get("players", []):
        code = resolve(team["team"]["abbreviation"])
        if code is None:
            raise ValueError("unknown_team")
        for table in team.get("statistics", []):
            keys = table.get("keys", [])
            for athlete in table.get("athletes", []):
                aid = int(athlete["athlete"]["id"])
                stat = dict(zip(keys, athlete.get("stats", [])))
                if athlete.get("didNotPlay"):
                    out[(code, aid)] = dict(appeared=False)
                elif all(k in stat for k in ("minutes", "points", "rebounds", "assists")):
                    out[(code, aid)] = dict(appeared=True, minutes=minutes_value(stat["minutes"]),
                                            pts=int(stat["points"]), reb=int(stat["rebounds"]), ast=int(stat["assists"]))
    # each team's player points must add to its final score, otherwise the box is not trusted for missing players
    for t, sc in final.items():
        pts = sum(v.get("pts", 0) for (tt, _), v in out.items() if tt == t and v["appeared"])
        out[("__score_ok__", t)] = dict(appeared=False, ok=pts == sc)
    return out


def conditional_pmf(unconditional, p_appear):
    if p_appear <= 0:
        raise ValueError("zero_probability_appearance")
    p = list(unconditional)
    p[0] -= 1 - p_appear
    p = [max(0., v / p_appear) for v in p]
    total = sum(p)
    return [v / total for v in p]  # correct only serialization rounding


def rps(p, outcome, cap):
    cumulative = 0.
    score = 0.
    for k in range(cap):
        cumulative += p[k]
        score += (cumulative - (outcome <= k)) ** 2
    return score / cap


def score(archive, audit, output_dir, fetch=False):
    output_dir = Path(output_dir)
    boxes = output_dir / "outcomes"
    boxes.mkdir(parents=True, exist_ok=True)
    metrics = defaultdict(list)
    exclusions = Counter()
    rows = []
    outcomes_meta = []
    for chosen in audit["selected"]:
        if chosen["horizon_min"] != 60:
            continue
        gid = chosen["game_id"]
        path = boxes / f"{gid}.json"
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={gid}"
        try:
            if not path.exists() and fetch:
                with urllib.request.urlopen(url, timeout=45) as response:
                    data = response.read()
                document = json.loads(data)
                box_players(document, gid)  # do not freeze a still-live box
                with path.open("xb") as fh:
                    fh.write(data)
                meta = dict(source_url=url, retrieved_utc=datetime.now(timezone.utc).isoformat(),
                            sha256=hashlib.sha256(data).hexdigest())
                path.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            actual = box_players(json.loads(path.read_bytes()), gid)
        except (OSError, ValueError) as error:
            exclusions[str(error)[:120]] += 1
            continue
        outcomes_meta.append(dict(game_id=gid, source_url=url, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        forecast = archive.read(chosen["path"])
        for player in forecast["players"]:
            key = (player["team"], player["aid"])
            game_teams = set(forecast.get("coverage", {}))
            box_teams = {t for t, _ in actual if t != "__score_ok__"}
            source = "box"
            if key not in actual:
                # Research convention (research/nba_minutes_test.py build: box minutes, else 0): a candidate absent from the final box did not
                # appear (mostly inactive players ruled Out). Applied only when the mapping and the box are verified; otherwise unknown.
                if box_teams != game_teams or key[0] not in game_teams:
                    exclusions["missing_unknown_team_mapping_mismatch"] += 1
                    continue
                if any(a == key[1] for t, a in actual if t != "__score_ok__"):
                    exclusions["missing_unknown_player_listed_for_other_team"] += 1
                    continue
                if not box_complete(actual, key[0]):
                    exclusions["missing_unknown_team_box_incomplete"] += 1
                    continue
                exclusions["missing_from_complete_box_scored_as_dnp"] += 1
                result, source = dict(appeared=False), "missing_dnp"
            else:
                result = actual[key]
            pa = player["p_appear"]
            appeared = result["appeared"]
            ll = -math.log(max(1e-12, pa if appeared else 1 - pa))
            versions = ("research_convention", "box_listed_only") if source == "box" else ("research_convention",)
            for mv in versions:
                metrics[mv + ":appearance_logloss"].append(ll)
            row = dict(game_id=gid, team=key[0], aid=key[1], appeared=appeared, outcome_source=source, appearance_logloss=ll)
            if appeared:
                for stat, cap in (("reb", 25), ("ast", 20)):
                    for version in ("v2", "v3"):
                        p = conditional_pmf(player[f"{stat}_{version}"], pa)
                        value = rps(p, result[stat], cap)
                        for mv in versions:
                            metrics[f"{mv}:{stat}_{version}_rps_given_appearing"].append(value)
                        row[f"{stat}_{version}_rps"] = value
                        row[f"{stat}_{version}_mean"] = sum(i * v for i, v in enumerate(p))
                    row[stat] = result[stat]
                row["minutes"] = result["minutes"]
            rows.append(row)
    return dict(label="Interim descriptive only; tiny selected sample, NOT an adoption or betting result",
                generated_utc=datetime.now(timezone.utc).isoformat(),
                audited_archive_commit=audit["source_commit"], player_games_matched=len(rows),
                appearing_player_games=sum(r["appeared"] for r in rows),
                metrics={k: dict(n=len(v), mean=sum(v)/len(v)) for k, v in metrics.items()},
                exclusions=dict(exclusions), outcome_sources=outcomes_meta, player_rows=rows,
                limitations=["No confidence/adoption verdict; fewer than the predeclared 30000 player-games.",
                             "Conditional scores omit DNPs; no assumption about market settlement.",
                             "Two versions are reported: research_convention (a candidate absent from a verified complete final box = did not appear) and box_listed_only (absent candidates excluded). Absent candidates with an unverified mapping or incomplete box are unknown in both.",
                             "No market edge or profit calculated without matched executable pre-cutoff quotes and fees.",
                             "Archive timing passed; report-coverage warnings still require review.",
                             "Score is normalized clipped RPS, not percentage accuracy."])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--audit", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fetch-outcomes", action="store_true")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit).read_text())
    result = score(GitArchive(args.repo, audit["source_commit"]), audit, args.output_dir, args.fetch_outcomes)
    Path(args.output_dir, "forward_scores_interim.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("player_rows", "outcome_sources")}, indent=2))
