#!/usr/bin/env python3
"""Build the signal/staking-split leaderboard — data/leaderboard_split.json.

Session arena/907c5baf-x1 (task N3). Requirement: separate 'signal' from
'staking' in the leaderboard so a lucky staking run cannot mask a bad signal.

  * The SIGNAL scorecard is the only thing rank is computed from. It uses
    staking-blind metrics: hit rate, flat-stake (1 unit) ROI, bootstrap CI,
    skill-test p-value, luck-removed ROI, parameter stability.
  * The STAKING scorecard is a separate, explicitly unranked diagnostic:
    drawdown, losing streak and volatility under a staking plan. Changing
    staking can never change rank (the rule is enforced here and checked by
    tools/verify_stores.py).
  * Two tiers of evidence are kept apart: official-track rows (blank + flagged
    until the verified results feed has graded bets) and the research-lab
    reference block (computed on the fingerprinted community-mirror backtest,
    labelled unverified).

Inputs (read-only): data/site/payload.json, data/processed/strategy_bets.csv,
data/results_feed.json.
Output: data/leaderboard_split.json
"""

from __future__ import annotations

import csv
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = "2026-11-14"
PAYLOAD = os.path.join(ROOT, "data", "site", "payload.json")
BETS = os.path.join(ROOT, "data", "processed", "strategy_bets.csv")
FEED = os.path.join(ROOT, "data", "results_feed.json")
OUT = os.path.join(ROOT, "data", "leaderboard_split.json")

MIRROR_URL = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
MIRROR_LABEL = "nflverse/nfldata games.csv (community mirror — not an official source)"


def staking_diagnostics() -> dict:
    per = defaultdict(list)
    with open(BETS, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                profit = float(r["profit"])
            except (KeyError, ValueError):
                continue
            per[r["strategy"]].append((r.get("gameday", ""), profit))
    out = {}
    for strat, series in per.items():
        series.sort(key=lambda x: x[0])
        cum = peak = dd = 0.0
        streak = max_streak = 0
        for _, p in series:
            cum += p
            peak = max(peak, cum)
            dd = max(dd, peak - cum)
            if p < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        n = len(series)
        out[strat] = {
            "n_bets": n,
            "max_drawdown_units": round(dd, 3),
            "longest_losing_streak": max_streak,
            "net_units_flat": round(cum, 3),
        }
    return out


def main() -> int:
    with open(PAYLOAD, encoding="utf-8") as f:
        payload = json.load(f)
    with open(FEED, encoding="utf-8") as f:
        feed = json.load(f)
    diag = staking_diagnostics()
    luck = {l["strategy"]: l for l in payload["luck"]}

    graded = feed["settlement_summary"]["markets_originated_and_settled"]

    signal_rows = []
    staking_rows = []
    for s in sorted(payload["leaderboard"], key=lambda x: x.get("rank", 999)):
        key = s["key"]
        l = luck.get(key, {})
        clean = l.get("clean_games", {})
        signal_rows.append({
            "rank": s.get("rank", ""),
            "strategy_id": key,
            "strategy": s["name"],
            "family": s.get("family", ""),
            "graded_bets": s["bets"],
            "hit_rate": round(s["hit_rate"], 4),
            "flat_stake_roi": round(s["roi"], 4),
            "ci_lo": round(s["ci_lo"], 4),
            "ci_hi": round(s["ci_hi"], 4),
            "p_value": round(s["p_value"], 5),
            "luck_removed_roi": round(clean.get("roi", 0.0), 4),
            "luck_profit_share_pct": round(l.get("luck_profit_share", 0.0), 2),
            "stability_share_positive": s.get("stability", {}).get("share_positive", ""),
            "gates_passed": "all 8" if s.get("all_passed") else ", ".join(
                g["key"] for g in s.get("gates", []) if not g["passed"]) + " failed",
            "eligibility": "ELIGIBLE (mirror reference)" if s.get("all_passed") else "NOT ELIGIBLE",
            "evidence_tier": "research-lab backtest on the community mirror (unverified)",
            "_source_url": MIRROR_URL,
            "_source_label": MIRROR_LABEL,
            "_source_org": "nflverse (community)",
            "_retrieved_at": GEN,
            "_flags": ["computed on the fingerprinted community mirror; not league-verified (F-12/I-10)"],
            "_verified": False,
        })
        d = diag.get(key, {})
        staking_rows.append({
            "strategy_id": key,
            "strategy": s["name"],
            "staking_plan": "flat 1 unit per bet (reference plan; any other plan awaits Q-32)",
            "staking_roi": round(s["roi"], 4),
            "max_drawdown_units": d.get("max_drawdown_units", ""),
            "longest_losing_streak": d.get("longest_losing_streak", ""),
            "net_units_flat": d.get("net_units_flat", ""),
            "rank_effect": "NONE — staking columns cannot change rank",
            "_source_url": MIRROR_URL,
            "_source_label": MIRROR_LABEL,
            "_source_org": "nflverse (community)",
            "_retrieved_at": GEN,
            "_flags": ["diagnostic only; computed on the community-mirror bet series"],
            "_verified": False,
        })

    official_row = {
        "rank": "",
        "strategy_id": "official-track",
        "strategy": "All live strategies (verified track)",
        "family": "",
        "graded_bets": "",
        "hit_rate": "",
        "flat_stake_roi": "",
        "ci_lo": "",
        "ci_hi": "",
        "p_value": "",
        "luck_removed_roi": "",
        "luck_profit_share_pct": "",
        "stability_share_positive": "",
        "gates_passed": "",
        "eligibility": "not evaluated",
        "evidence_tier": "verified results feed",
        "_source_url": "https://www.nfl.com/schedules/2026/by-week/week-10",
        "_source_label": "NFL.com — Week 10 schedule (verified results feed)",
        "_source_org": "NFL",
        "_retrieved_at": GEN,
        "_flags": [
            f"no graded strategy bets yet (the feed has {graded} settled markets from 1 game); "
            "cells stay blank until strategies are pre-registered and graded — never filled from the mirror",
        ],
        "_verified": True,
    }

    doc = {
        "dataset": "leaderboard_split",
        "title": "Leaderboard — signal separated from staking",
        "generated_at": GEN,
        "policy": {
            "ranking_rule": ("rank is computed from SIGNAL columns only (eligibility "
                             "gates first, then bootstrap CI lower bound, then p-value); "
                             "staking columns are diagnostics and can never change rank"),
            "signal_columns": ["graded_bets", "hit_rate", "flat_stake_roi", "ci_lo",
                               "ci_hi", "p_value", "luck_removed_roi",
                               "luck_profit_share_pct", "stability_share_positive"],
            "staking_columns": ["staking_plan", "staking_roi", "max_drawdown_units",
                                "longest_losing_streak", "net_units_flat"],
            "luck_rule": ("ROI is re-measured with one-score games (margin <= 8) and "
                          "blowouts (margin >= 25) removed; a signal that survives only "
                          "on luck games is flagged"),
            "blank_rule": "an ungraded cell stays blank and is flagged; never inferred",
        },
        "signal_scorecard": {
            "columns": ["rank", "strategy_id", "strategy", "family", "graded_bets",
                        "hit_rate", "flat_stake_roi", "ci_lo", "ci_hi", "p_value",
                        "luck_removed_roi", "luck_profit_share_pct",
                        "stability_share_positive", "gates_passed", "eligibility",
                        "evidence_tier"],
            "rows": [official_row] + signal_rows,
        },
        "staking_scorecard": {
            "ranked": False,
            "columns": ["strategy_id", "strategy", "staking_plan", "staking_roi",
                        "max_drawdown_units", "longest_losing_streak", "net_units_flat",
                        "rank_effect"],
            "rows": staking_rows,
        },
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"signal scorecard : {len(doc['signal_scorecard']['rows'])} rows "
          f"(1 official-track + {len(signal_rows)} mirror reference)")
    print(f"staking scorecard: {len(staking_rows)} rows (unranked by rule)")
    return 0


if __name__ == "__main__":
    main()
