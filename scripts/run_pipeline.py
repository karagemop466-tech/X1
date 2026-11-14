#!/usr/bin/env python3
"""Run the full X1 research pipeline and write every published artefact.

Usage:
    python3 scripts/run_pipeline.py

Outputs
-------
data/processed/*.csv   tables that back the site
data/site/*.json       payloads consumed by the site generator
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

from x1 import config, correlation, evaluation, gates, injuries as inj, ingest, leaderboard, model, prep, props, strategies


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> None:
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    config.SITE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- data
    log("syncing raw data")
    records = ingest.sync()
    manifest = [
        {
            "name": r.name,
            "repo": r.repo,
            "path": r.path,
            "source_key": r.source_key,
            "url": r.url,
            "bytes": r.bytes,
            "sha256": r.sha256,
            "status": r.status,
        }
        for r in records
    ]
    (config.DATA_DIR / "raw_manifest.json").write_text(json.dumps(manifest, indent=2))

    log("preparing games + walk-forward Elo")
    games = prep.load_games()
    elo = prep.walk_forward_elo(games)
    games = prep.build_features(elo.games)

    log("fitting originated-line model (walk-forward Poisson)")
    line_model = model.fit_line_model(games)
    games = line_model.frame
    model_summary = model.model_summary(line_model)
    market_all = model.compare_to_market(line_model)
    market_recent = model.compare_to_market(line_model, seasons=[2021, 2022, 2023, 2024, 2025, 2026])
    market_holdout = model.compare_to_market(line_model, seasons=[config.TEST_SEASON])

    keep = [
        "game_id", "season", "game_type", "week", "gameday", "away_team", "away_score",
        "home_team", "home_score", "result", "margin", "total_points", "market_spread",
        "market_total", "home_covers", "over", "elo_home_pre", "elo_away_pre",
        "elo_diff_home", "model_spread", "model_total", "model_home_win_prob",
        "spread_delta", "total_delta", "away_rest", "home_rest", "rest_diff", "roof",
        "temp", "wind", "neutral_site", "home_qb_name", "away_qb_name", "stadium",
        "referee", "home_coach", "away_coach",
    ]
    games[keep].to_csv(config.PROCESSED_DIR / "games_modeled.csv", index=False)
    line_model.season_diagnostics.to_csv(config.PROCESSED_DIR / "model_diagnostics.csv", index=False)

    # ----------------------------------------------------------- strategies
    log("evaluating strategy library (walk-forward)")
    registry = strategies.registry()
    results = []
    for strat in registry:
        t0 = time.time()
        res = evaluation.evaluate_strategy(strat, games)
        results.append(res)
        log(f"  {strat.key:22s} bets={len(res.bets):5d} roi="
            f"{float(res.bets['profit'].mean()) * 100 if len(res.bets) else float('nan'):+.2f}% "
            f"({time.time() - t0:.1f}s)")

    log("building leaderboard and gates")
    ranked, leader_meta = leaderboard.build_leaderboard(results, games)
    baselines = leader_meta["baselines"]

    all_bets = pd.concat([r.bets for r in results if len(r.bets)], ignore_index=True) if results else pd.DataFrame()
    if len(all_bets):
        all_bets.to_csv(config.PROCESSED_DIR / "strategy_bets.csv", index=False)

    bets_by_strategy = {r.key: r.bets for r in results}
    corr = correlation.strategy_correlations(bets_by_strategy)
    if not corr.empty:
        corr.to_csv(config.PROCESSED_DIR / "strategy_correlations.csv")
    pairwise = correlation.pairwise_detail(bets_by_strategy)

    luck_rows = []
    for r in results:
        if not len(r.bets):
            continue
        la = correlation.luck_analysis(r.bets, games)
        if la:
            la["strategy"] = r.key
            luck_rows.append(la)
    luck = pd.DataFrame(luck_rows)
    if len(luck):
        luck.to_csv(config.PROCESSED_DIR / "luck_analysis.csv", index=False)

    # -------------------------------------------------------------- props
    log("building prop models")
    try:
        pstats = props.load_player_stats()
        pstats26 = props.load_player_stats_2026()
        family_rows = props.prop_family_stats(pstats)
        same_game = props.same_game_prop_correlations(pstats)
        combos = props.prop_combo_break_even(same_game)
        current_lines = props.current_week_prop_lines(pstats26)
        pd.DataFrame(family_rows).to_csv(config.PROCESSED_DIR / "prop_family_stats.csv", index=False)
        pd.DataFrame(combos).to_csv(config.PROCESSED_DIR / "prop_combos.csv", index=False)
        prop_payload = {
            "families": family_rows,
            "combos": combos,
            "same_game": same_game,
            "current_lines": current_lines,
        }
    except Exception as exc:  # pragma: no cover
        log(f"  prop build failed: {exc}")
        prop_payload = {"families": [], "combos": [], "same_game": {}, "error": str(exc)}

    # ---------------------------------------------------------- injuries
    log("building injury + depth analysis")
    try:
        inj_df = inj.load_injuries()
        official = inj.load_official_current()
        try:
            from x1 import props as _props
            pstats26 = _props.load_player_stats_2026()
        except Exception:
            pstats26 = None
        depth = inj.load_depth_charts()
        rosters = inj.load_weekly_rosters()
        current = inj.current_injury_table(inj_df, config.CURRENT_WEEK, official)
        deficiency = inj.usage_deficiency_table(inj_df, depth, rosters, config.CURRENT_WEEK, games, official, pstats26)
        # The mirror snapshot for the newest week is incomplete (game-status
        # designations are added after publication), so use the newest week
        # with a complete set of designations.
        status_counts = inj_df[inj_df["status"] != ""].groupby("week").size()
        complete_weeks = status_counts[status_counts >= 25].index.tolist()
        machine_week = int(max(complete_weeks)) if complete_weeks else int(inj_df["week"].max())
        deficiency_machine = inj.usage_deficiency_table(inj_df, depth, rosters, machine_week, games, None, pstats26)
        effect = inj.injury_effect_on_covering(inj_df, games)
        depth_status = inj.depth_status_table(pstats26, current, config.CURRENT_WEEK)
        inj_summary = inj.injury_summary(inj_df, official)
        pd.DataFrame(current).to_csv(config.PROCESSED_DIR / "injuries_current.csv", index=False)
        pd.DataFrame(deficiency).to_csv(config.PROCESSED_DIR / "depth_deficiency.csv", index=False)
        pd.DataFrame(deficiency_machine).to_csv(config.PROCESSED_DIR / "depth_deficiency_machine.csv", index=False)
        pd.DataFrame(effect).to_csv(config.PROCESSED_DIR / "injury_effect.csv", index=False)
        injury_payload = {
            "current": current,
            "deficiency": deficiency,
            "deficiency_machine": deficiency_machine,
            "depth_status": depth_status,
            "effect": effect,
            "summary": inj_summary,
            "history": inj_df,
        }
    except Exception as exc:  # pragma: no cover
        log(f"  injury build failed: {exc}")
        injury_payload = {"current": [], "deficiency": [], "effect": [], "error": str(exc)}

    # -------------------------------------------------------- site payload
    log("writing site payloads")
    payload = {
        "model": {
            "summary": model_summary,
            "market_all": market_all,
            "market_recent": market_recent,
            "market_holdout": market_holdout,
            "diagnostics": line_model.season_diagnostics.to_dict("records"),
        },
        "leaderboard": [
            {
                k: v for k, v in entry.items()
                if k not in ("bets_frame", "gate_report", "param_history", "sensitivity")
            } | {
                "gates": entry["gate_report"].to_dict()["gates"],
                "all_passed": entry["gate_report"].all_passed,
                "param_history": entry["param_history"],
                "sensitivity": entry["sensitivity"],
            }
            for entry in ranked
        ],
        "baselines": baselines,
        "correlations": {
            "matrix": corr.to_dict() if not corr.empty else {},
            "pairwise": pairwise,
        },
        "luck": luck.to_dict("records") if len(luck) else [],
        "props": prop_payload,
        "injuries": {
            "current": injury_payload.get("current", []),
            "deficiency": injury_payload.get("deficiency", []),
            "deficiency_machine": injury_payload.get("deficiency_machine", []),
            "depth_status": injury_payload.get("depth_status", []),
            "effect": injury_payload.get("effect", []),
            "summary": injury_payload.get("summary", {}),
        },
        "manifest": manifest,
    }
    (config.SITE_DATA_DIR / "payload.json").write_text(json.dumps(payload, indent=2, default=str))
    log("done")


if __name__ == "__main__":
    main()
