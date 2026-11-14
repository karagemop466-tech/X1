#!/usr/bin/env python3
"""Separate 'signal' from 'staking' on the strategy leaderboard (T18).

Session `arena-1d3600f8-x1`. Owner requirement:

> Separate 'signal' from 'staking' in the leaderboard so a lucky staking run
> cannot mask a bad signal.

Design:

  SIGNAL block  — pure pick quality under FLAT 1-unit stakes on every bet.
                   Hit rate vs break-even, z, Wilson interval, window-halves
                   stability, luck share, top-5%-trimmed ROI. A strategy's
                   signal grade depends on NOTHING stake-sized.

  STAKING block — bankroll behaviour: ROI and max drawdown under (a) flat
                   stakes and (b) a pre-registered variance-amplifying rule
                   (2 units after a win, 1 after a loss) used purely to
                   demonstrate that staking can move returns without moving
                   the signal. Also single-bet concentration.

  RULE          — final grade = min(signal, staking). A failing signal can
                   never be rescued by staking: `eligible_for_ranking` is true
                   only if the SIGNAL gate passes first. Staking grades scale
                   rewards among signal-passers and nothing else.

Provenance: outcomes/odds come from the third-party mirror strategy ledger
(data/processed/strategy_bets.csv) and are labelled `mirror-window` throughout;
CLV is blank (no price feed, Q-02). The same rule is applied to the official
ledger in data/leaderboard.json, which stays unranked until graded results
exist from official feeds.

Outputs: data/leaderboard_signal_staking.csv, data/leaderboard_signal_staking.json
"""

from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_CSV = os.path.join(ROOT, "data", "leaderboard_signal_staking.csv")
OUT_JSON = os.path.join(ROOT, "data", "leaderboard_signal_staking.json")
BETS = os.path.join(ROOT, "data", "processed", "strategy_bets.csv")
LUCK = os.path.join(ROOT, "data", "processed", "luck_analysis.csv")

BANKROLL_U = 100.0
BE110 = 110.0 / 210.0
MIRROR_SRC = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def max_drawdown(profits: list[float]) -> float:
    peak, dd = 0.0, 0.0
    cum = 0.0
    for p in profits:
        cum += p
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


def main() -> int:
    bets_by: dict[str, list[dict]] = defaultdict(list)
    with open(BETS, encoding="utf-8") as fh:
        for b in csv.DictReader(fh):
            bets_by[b["strategy"]].append(b)
    for s in bets_by:
        bets_by[s].sort(key=lambda b: (b["gameday"], b["game_id"]))

    luck = {}
    with open(LUCK, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            luck[r["strategy"]] = r

    rows = []
    for strat in sorted(bets_by):
        bs = bets_by[strat]
        n = len(bs)
        wins = sum(1 for b in bs if float(b["profit"]) > 0)
        losses = sum(1 for b in bs if float(b["profit"]) < 0)
        pushes = n - wins - losses
        hit = wins / n if n else 0.0
        lo, hi = wilson(wins, n)
        z = (hit - BE110) / math.sqrt(BE110 * (1 - BE110) / n) if n else 0.0

        flat_profits = [float(b["profit"]) for b in bs]
        flat_units = sum(flat_profits)
        flat_roi = flat_units / n * 100 if n else 0.0

        # top-5%-trimmed ROI (gates scoring rule: report raw and trimmed together)
        srt = sorted(flat_profits)
        trim = max(1, int(n * 0.05))
        trimmed = srt[trim:-trim] if n > 2 * trim else srt
        trimmed_roi = sum(trimmed) / len(trimmed) * 100 if trimmed else 0.0

        # window-halves stability
        half = n // 2
        roi_h1 = sum(flat_profits[:half]) / half * 100 if half else 0.0
        roi_h2 = sum(flat_profits[half:]) / (n - half) * 100 if n - half else 0.0

        # staking contrast: momentum rule 2u after win, 1u after loss
        mom_profits, stake = [], 1.0
        for b in bs:
            p = float(b["profit"])
            mom_profits.append(p * stake)
            stake = 2.0 if p > 0 else 1.0
        mom_roi = sum(mom_profits) / n * 100 if n else 0.0

        dd_flat = max_drawdown(flat_profits)
        dd_mom = max_drawdown(mom_profits)

        # concentration: largest single bet as share of gross wins
        gross_win = sum(p for p in flat_profits if p > 0)
        max_single_share = (max(flat_profits) / gross_win * 100) if gross_win > 0 else 0.0

        lk = luck.get(strat, {})
        luck_share = lk.get("luck_profit_share", "")

        # ---------------------------------------------------------- verdicts
        sig_fail = []
        if n < 500:
            sig_fail.append(f"n={n} < 500 (G1)")
        if z < 1.96:
            sig_fail.append(f"z={z:.2f} < 1.96 (G2)")
        if not (lo > 0.0 and hi > 0.0) and not (lo < 0 and hi < 0):
            pass
        if lo <= BE110 <= hi:
            sig_fail.append("hit-rate interval contains break-even (G2)")
        if roi_h1 * roi_h2 < 0:
            sig_fail.append("edge sign not stable across window halves (G4)")
        signal_gate = "PASS" if not sig_fail else "FAIL"

        st_fail = []
        if dd_mom > 0.25 * BANKROLL_U:
            st_fail.append(f"momentum-rule drawdown {dd_mom:.1f}u > 25% of bankroll (G5)")
        staking_gate = "PASS" if not st_fail else "FAIL"

        eligible = signal_gate == "PASS" and staking_gate == "PASS"

        rows.append({
            "strategy_id": strat,
            "market_family": "parlay/prop-combo" if strat.startswith("P_") else "single",
            # ---------------- signal block (flat stakes only)
            "signal_bets": n,
            "signal_wins": wins, "signal_losses": losses, "signal_pushes": pushes,
            "signal_hit_rate_pct": f"{hit * 100:.2f}",
            "signal_hit_ci95_lo_pct": f"{lo * 100:.2f}",
            "signal_hit_ci95_hi_pct": f"{hi * 100:.2f}",
            "signal_z_vs_breakeven": f"{z:.2f}",
            "signal_flat_roi_pct": f"{flat_roi:.2f}",
            "signal_flat_roi_trimmed5_pct": f"{trimmed_roi:.2f}",
            "signal_roi_first_half_pct": f"{roi_h1:.2f}",
            "signal_roi_second_half_pct": f"{roi_h2:.2f}",
            "signal_luck_profit_share": str(luck_share),
            "signal_mean_clv": "",  # blank: no price feed (Q-02)
            "signal_gate": signal_gate,
            "signal_gate_reasons": "; ".join(sig_fail) if sig_fail else "all signal criteria met",
            # ---------------- staking block
            "staking_flat_units": f"{flat_units:.2f}",
            "staking_flat_max_drawdown_u": f"{dd_flat:.2f}",
            "staking_momentum_roi_pct": f"{mom_roi:.2f}",
            "staking_momentum_max_drawdown_u": f"{dd_mom:.2f}",
            "staking_max_single_bet_share_pct": f"{max_single_share:.2f}",
            "staking_gate": staking_gate,
            "staking_gate_reasons": "; ".join(st_fail) if st_fail else "drawdown within cap",
            # ---------------- combined
            "eligible_for_ranking": "yes" if eligible else "no",
            "final_status": ("paper-promotable" if eligible else
                            ("paper-only (signal fail)" if signal_gate == "FAIL" else "paper-only (staking risk)")),
            "rule": "final grade = min(signal, staking); staking can never rescue a failing signal",
            "outcome_source": "mirror-window ledger (third-party, NOT official)",
            "odds_source": "mirror-window ledger (third-party, NOT official)",
            "source_url": MIRROR_SRC,
        })

    cols = list(rows[0])
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    doc = {
        "dataset": "leaderboard_signal_staking",
        "generated_at": "2026-11-14",
        "rule": {
            "separation": "signal metrics are computed at flat 1-unit stakes only; staking metrics never enter the signal grade",
            "final_grade": "min(signal, staking)",
            "masking_protection": "a lucky staking run cannot mask a bad signal: eligible_for_ranking requires signal_gate=PASS first; staking only scales rewards among signal-passers",
            "gates_referenced": ["G1 sample size", "G2 skill above variance", "G4 robustness (window halves)", "G5 risk of ruin (drawdown cap)"],
        },
        "provenance": {
            "outcomes": "mirror-window ledger (nflverse/nfldata) — third-party, NOT official; the official-only board in data/leaderboard.json stays unranked until official graded results exist",
            "odds": "mirror-window ledger — third-party, NOT official (Q-02)",
            "clv": "blank — no price feed (Q-02)",
            "source_url": MIRROR_SRC,
        },
        "columns": cols,
        "rows": rows,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)

    npass = sum(1 for r in rows if r["eligible_for_ranking"] == "yes")
    print(f"strategies graded : {len(rows)}")
    print(f"signal gate PASS  : {sum(1 for r in rows if r['signal_gate'] == 'PASS')}")
    print(f"staking gate PASS : {sum(1 for r in rows if r['staking_gate'] == 'PASS')}")
    print(f"eligible to rank  : {npass}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
