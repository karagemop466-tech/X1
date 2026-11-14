"""Leaderboard and reward scoring.

Reward formula (documented on the site):

    reward = 1000 * ROI * min(1, bets / 300) * confidence

where ``confidence`` is the share of the bootstrap confidence-interval lower
bound that survives the ROI estimate (1.0 when the whole interval sits above
zero, 0 for a strategy whose interval crosses zero).  A strategy that fails any
validation gate earns zero reward, so the leaderboard only ever rewards
strategies that are defensible.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import config, gates
from .correlation import pairwise_detail
from .evaluation import StrategyResult, sensitivity_table, stability


def _confidence(roi: float, ci_lo: float) -> float:
    if not np.isfinite(roi) or roi <= 0:
        return 0.0
    if not np.isfinite(ci_lo) or ci_lo <= 0:
        return 0.0
    return float(min(1.0, max(0.0, ci_lo / roi)))


def build_leaderboard(
    results: List[StrategyResult],
    games: pd.DataFrame,
) -> Tuple[List[Dict], Dict]:
    all_bets = (
        pd.concat([r.bets for r in results if len(r.bets)], ignore_index=True)
        if results else pd.DataFrame()
    )
    baselines = gates.naive_baselines(games, all_bets)

    entries: List[Dict] = []
    for res in results:
        bets = res.bets
        n = len(bets)
        r = gates.roi(bets) if n else float("nan")
        lo, hi, mean = gates.bootstrap_ci(bets["profit"].values.astype(float)) if n else (np.nan,) * 3
        pval = gates.permutation_pvalue(bets["profit"].values.astype(float)) if n else np.nan

        merged = (
            bets.merge(games[["game_id", "margin"]], on="game_id", how="left", suffixes=("", "_g"))
            if n else pd.DataFrame()
        )
        if n:
            margin = merged["margin_g"] if "margin_g" in merged.columns else merged.get("margin")
            clean = merged[
                (margin.abs() > config.ONE_SCORE_MAX_MARGIN)
                & (margin.abs() < config.BLOWOUT_MIN_MARGIN)
            ]
        else:
            clean = merged

        entries.append({
            "key": res.key,
            "name": res.strategy.name,
            "family": res.strategy.family,
            "description": res.strategy.description,
            "source_keys": res.strategy.source_keys,
            "bets": int(n),
            "roi": r,
            "hit_rate": gates.hit_rate(bets) if n else float("nan"),
            "profit": float(bets["profit"].sum()) if n else 0.0,
            "ci_lo": lo,
            "ci_hi": hi,
            "p_value": pval,
            "seasons": sorted(set(bets["season"].tolist())) if n else [],
            "first_season": int(min(bets["season"])) if n else None,
            "last_season": int(max(bets["season"])) if n else None,
            "clean_bets": clean,
            "stability": stability(res),
            "param_history": res.param_history,
            "sensitivity": sensitivity_table(res),
            "bets_frame": bets,
        })

    # --- Gate 8: non-redundancy, applied in ROI order ----------------------
    ordered = sorted(entries, key=lambda e: (-(e["roi"] if np.isfinite(e["roi"]) else -9)))
    accepted: List[Dict] = []
    for entry in ordered:
        accepted_frames = {e["key"]: e["bets_frame"] for e in accepted}
        max_corr, partner = float("nan"), None
        if accepted_frames:
            details = pairwise_detail({**accepted_frames, entry["key"]: entry["bets_frame"]})
            worst = None
            for d in details:
                if entry["key"] in (d["strategy_a"], d["strategy_b"]):
                    if worst is None or abs(d["correlation"]) > abs(worst["correlation"]):
                        worst = d
            if worst is not None:
                max_corr = worst["correlation"]
                partner = worst["strategy_b"] if worst["strategy_b"] != entry["key"] else worst["strategy_a"]

        report = gates.evaluate(
            entry["key"],
            entry["bets_frame"],
            baselines=baselines,
            clean_bets=entry["clean_bets"],
            stability=entry["stability"],
            max_correlation=max_corr,
            correlation_partner=partner,
        )
        entry["gate_report"] = report
        entry["max_correlation"] = max_corr
        entry["correlation_partner"] = partner
        if report.all_passed:
            accepted.append(entry)

    for entry in entries:
        report = entry["gate_report"]
        if report.all_passed:
            conf = _confidence(entry["roi"], entry["ci_lo"])
            entry["confidence"] = conf
            entry["reward"] = float(
                1000.0 * entry["roi"] * min(1.0, entry["bets"] / 300.0) * conf
            )
        else:
            entry["confidence"] = 0.0
            entry["reward"] = 0.0
        entry["failed_gates"] = [g.key for g in report.gates if not g.passed]
        entry["gate_summary"] = {g.key: g.passed for g in report.gates}

    ranked = sorted(entries, key=lambda e: (-e["reward"], -(e["roi"] if np.isfinite(e["roi"]) else -9)))
    for i, entry in enumerate(ranked, start=1):
        entry["rank"] = i

    return ranked, {"baselines": baselines}
