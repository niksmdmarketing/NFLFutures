"""Read-only paired replay of the live NFL team-attempt feature mismatch."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import core as C
from build import BASE, OUT
from run import model, logscore

RULE = Path(__file__).with_name("LIVE_INPUT_ALIGNMENT_RULE.md")
DEST = BASE / "outputs" / "nfl_live_input_alignment_20261026"
PARAMS = Path(__file__).resolve().parents[2] / "model" / "nfl_player_props_v1.json"
TEAM_FILE = OUT / "teams.parquet"
RESULTS_FILE = OUT / "results.json"
KEY = ["game_id", "team", "season"]
NEUTRAL = ["own_pass_off", "opp_pass_def", "elo_gap"]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def predict_pmf(mu: np.ndarray, dispersion: float) -> np.ndarray:
    return C.nb_pmf(np.clip(mu, 5, 70), dispersion, 100)


def score(frame: pd.DataFrame, pmf: np.ndarray, label: str, seed: int) -> pd.DataFrame:
    y = frame.actual_team_att.to_numpy(int)
    assert np.all((y >= 0) & (y < 100))
    assert np.allclose(pmf.sum(axis=1), 1) and np.all(pmf >= 0)
    rng = np.random.default_rng(seed)
    uniform = rng.random(len(frame))
    out = frame[KEY + ["actual_team_att"]].copy()
    out["variant"] = label
    out["rps"] = C.rps(pmf, y, 60)
    out["log_score"] = logscore(pmf, y)
    out["predicted_mean"] = pmf @ np.arange(pmf.shape[1])
    out["mean_error"] = out.predicted_mean - y
    out["pit"] = C.pit(pmf, y, uniform)
    return out


def metrics(z: pd.DataFrame) -> dict:
    return {
        "n": int(len(z)),
        "rps": float(z.rps.mean()),
        "log_score": float(z.log_score.mean()),
        "mean_predicted": float(z.predicted_mean.mean()),
        "mean_actual": float(z.actual_team_att.mean()),
        "mean_error": float(z.mean_error.mean()),
        "pit_deciles": (np.histogram(z.pit, np.linspace(0, 1, 11))[0] / len(z)).tolist(),
    }


def main() -> None:
    if DEST.exists():
        raise FileExistsError(f"Create-only output already exists: {DEST}")
    protected = [TEAM_FILE, RESULTS_FILE, PARAMS, RULE]
    hashes = {str(p): sha(p) for p in protected}
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    teams = pd.read_parquet(TEAM_FILE)
    teams = teams[teams.season.between(2018, 2025) & teams.actual_team_att.notna()].copy()
    teams["actual_team_att"] = teams.actual_team_att.astype(int)
    assert not teams.duplicated(["game_id", "team"]).any()
    assert teams[C.VOLUME_FEATURES].notna().all().all()
    # Live treats these three unavailable inputs as neutral training-mean imputations.
    neutral_values = dict(zip(params["team_attempts"]["features"], params["team_attempts"]["mean"]))
    for col in NEUTRAL:
        teams[col] = float(neutral_values[col])

    rows = []
    fold_summary = {}
    for year in range(2021, 2026):
        train = teams[teams.season.between(2018, year - 1)].copy()
        test = teams[teams.season.eq(year)].copy().reset_index(drop=True)
        assert len(train) and len(test) and train.season.max() < year
        estimator = model("volume").fit(train[C.VOLUME_FEATURES], train.actual_team_att)
        train_mu = np.clip(estimator.predict(train[C.VOLUME_FEATURES]), 5, 70)
        dispersion = C.fit_nb(train.actual_team_att, train_mu)
        corrected_mu = np.clip(estimator.predict(test[C.VOLUME_FEATURES]), 5, 70)
        live = test.copy()
        live["opp_att"] = live["own_att"]  # reproduces the live join's self-match
        live_mu = np.clip(estimator.predict(live[C.VOLUME_FEATURES]), 5, 70)
        corrected_p = predict_pmf(corrected_mu, dispersion)
        live_p = predict_pmf(live_mu, dispersion)
        rows.extend([
            score(test, corrected_p, "corrected_opponent_allowed", 20261023 + year),
            score(test, live_p, "current_live_self_join", 20261023 + year),
        ])
        fold_summary[str(year)] = {
            "train_rows": int(len(train)), "test_rows": int(len(test)),
            "train_seasons": [int(train.season.min()), int(train.season.max())],
            "dispersion": float(dispersion),
            "corrected": metrics(score(test, corrected_p, "corrected", 20261023 + year)),
            "current_live": metrics(score(test, live_p, "live", 20261023 + year)),
        }

    paired = pd.concat(rows, ignore_index=True)
    wide = paired.pivot(index=KEY, columns="variant", values="rps").reset_index()
    wide["gain"] = wide["current_live_self_join"] - wide["corrected_opponent_allowed"]
    season_means = wide.groupby("season").gain.mean()
    season_counts = wide.groupby("season").size()
    rng = np.random.default_rng(20261023)
    seasons = season_means.index.to_numpy()
    season_sums = (season_means * season_counts).to_numpy()
    counts = season_counts.to_numpy()
    draw = rng.integers(0, len(seasons), size=(4000, len(seasons)))
    lower = float(np.quantile(season_sums[draw].sum(axis=1) / counts[draw].sum(axis=1), .05))

    # Descriptive replay with exactly the frozen deployed coefficients and dispersion.
    frozen = params["team_attempts"]
    X = teams[teams.season.between(2021, 2025)].copy().reset_index(drop=True)
    xv = X[C.VOLUME_FEATURES].to_numpy(float)
    means = np.asarray(frozen["mean"], float); scales = np.asarray(frozen["scale"], float)
    coef = np.asarray(frozen["coef"], float)
    frozen_corrected_mu = np.exp(frozen["intercept"] + ((xv - means) / scales) @ coef)
    frozen_live = X.copy(); frozen_live["opp_att"] = frozen_live["own_att"]
    frozen_x = frozen_live[C.VOLUME_FEATURES].to_numpy(float)
    frozen_live_mu = np.exp(frozen["intercept"] + ((frozen_x - means) / scales) @ coef)
    frozen_variants = pd.concat([
        score(X, predict_pmf(frozen_corrected_mu, frozen["dispersion"]), "corrected_opponent_allowed", 20261023),
        score(X, predict_pmf(frozen_live_mu, frozen["dispersion"]), "current_live_self_join", 20261023),
    ], ignore_index=True)

    result = {
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "evaluation": "paired walk-forward team pass-attempt feature-alignment replay",
        "seasons": [2021, 2022, 2023, 2024, 2025],
        "folds": fold_summary,
        "walk_forward": {
            "corrected": metrics(paired[paired.variant.eq("corrected_opponent_allowed")]),
            "current_live": metrics(paired[paired.variant.eq("current_live_self_join")]),
            "paired_mean_rps_gain": float(wide.gain.mean()),
            "relative_rps_reduction": float(wide.gain.mean() / paired[paired.variant.eq("current_live_self_join")].rps.mean()),
            "season_cluster_bootstrap_95pct_lower": lower,
            "seasons_improved": int((season_means > 0).sum()),
            "season_mean_gains": {str(int(y)): float(v) for y, v in season_means.items()},
        },
        "frozen_parameter_diagnostic_only": {
            "reason_not_independent": "Frozen parameters were fit through 2025, including the evaluated seasons.",
            "corrected": metrics(frozen_variants[frozen_variants.variant.eq("corrected_opponent_allowed")]),
            "current_live": metrics(frozen_variants[frozen_variants.variant.eq("current_live_self_join")]),
        },
        "limitations": [
            "Historical inputs are revised present-day nflverse files, not archived point-in-time vintages.",
            "This evaluates one team-volume feature only; it does not evaluate player role, availability, coverage, markets, or profitability.",
            "The challenger is not forward-archived and does not change the frozen live model.",
        ],
        "protected_inputs_unchanged": True,
    }
    for p, digest in hashes.items():
        assert sha(Path(p)) == digest, f"Protected input changed: {p}"
    DEST.mkdir(parents=True, exist_ok=False)
    (DEST / "rule.md").write_bytes(RULE.read_bytes())
    paired.to_parquet(DEST / "paired_scores.parquet", index=False)
    frozen_variants.to_parquet(DEST / "frozen_parameter_diagnostic.parquet", index=False)
    (DEST / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (DEST / "manifest.json").write_text(json.dumps({
        "inputs": hashes,
        "outputs": {p.name: sha(p) for p in DEST.iterdir() if p.is_file()},
        "market_inputs": False,
    }, indent=2), encoding="utf-8")
    report = [
        "# NFL live input alignment audit — 26 October 2026",
        "",
        "## Result",
        "",
        f"Walk-forward corrected RPS: {result['walk_forward']['corrected']['rps']:.5f}; current-live self-join RPS: {result['walk_forward']['current_live']['rps']:.5f}.",
        f"Paired relative RPS reduction: {result['walk_forward']['relative_rps_reduction']:.2%}; seasons improved: {result['walk_forward']['seasons_improved']}/5; season-cluster bootstrap 95% lower bound: {lower:.6f}.",
        "",
        "The paired replay refits each season using preceding seasons only and changes only the `opp_att` mapping. See the season table below for consistency.",
        "",
        "| Held-out season | Rows | Corrected RPS | Current-live RPS | RPS gain |",
        "|---:|---:|---:|---:|---:|",
    ]
    for year, fold in fold_summary.items():
        corrected = fold["corrected"]["rps"]; current_live = fold["current_live"]["rps"]
        report.append(f"| {year} | {fold['test_rows']} | {corrected:.5f} | {current_live:.5f} | {current_live-corrected:.5f} |")
    report += [
        "",
        "## Interpretation",
        "",
        "The live feature join is misaligned with the historical definition: it assigns each team's own attempts to `allowed`, then uses that same team's value as `opp_att`. The corrected feature uses the opponent's lagged attempts allowed, matching the historical feature definition. This report evaluates forecast-score impact only; it does not prove market edge or authorize changing the frozen model.",
        "",
        "The frozen-parameter replay is included separately in `results.json` and is descriptive only because those parameters were fit through 2025. Historical input-vintage limitations also apply.",
        "",
        "The active live pipeline, parameter file, website, archive, and workflows were not modified. No forward challenger archive was started.",
        "",
        "Paired row-level scores and input hashes are saved beside this report.",
    ]
    (DEST / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    # Update final manifest to include the report itself.
    manifest = json.loads((DEST / "manifest.json").read_text(encoding="utf-8"))
    manifest["outputs"] = {p.name: sha(p) for p in DEST.iterdir() if p.is_file() and p.name != "manifest.json"}
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(result["walk_forward"], indent=2))


if __name__ == "__main__":
    main()
