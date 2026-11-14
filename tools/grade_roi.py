#!/usr/bin/env python3
"""Grade bets against the verified results feed and compute ROI.

Session `arena-1d3600f8-x1` (T16). This is the "backtests and ROI can be
computed at all" piece: every outcome is settled from the official verified
results feed (data/results/verified_results_2026.csv, each row sourced to its
nfl.com game page), and every graded bet row carries the game's official URL.

Provenance rules (nothing is hidden):
  * outcomes  -> official (verified results feed)
  * prices    -> conventional -110 flat stake, an explicit assumption, because
                 no official or licensed price source exists (Q-02). ROI
                 computed at -110 is labelled `assumed_-110` everywhere.
  * lines     -> the model's own fair lines are our computations; the market
                 benchmark line comes from the nflverse mirror (data/processed/
                 games_modeled.csv) and is labelled third-party, not official.

Strategies graded (registered here, deterministic):
  MODEL_SIDE_t  — bet the model's side vs the market spread when |model-market|
                  disagreement >= t points (t = 1, 3, 5).
  MODEL_TOTAL_t — same idea on the total.
  BASE_HOME_ATS — home team against the spread, every game.
  BASE_OVER     — over the market total, every game.

Also reports model accuracy against verified outcomes (MAE on spread and
total), which needs no prices at all.

Outputs:
  data/results/graded_bets.csv   (one row per graded bet, with source URL)
  data/results/roi_summary.csv   (per-strategy ROI at assumed -110)
"""

from __future__ import annotations

import csv
import math
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "results")
PRICE_NOTE = "assumed -110 flat — no official price source exists (Q-02)"
MODEL_NOTE = "model fair line: our own computation (walk-forward, games_modeled.csv)"
MIRROR_NOTE = "market benchmark: nflverse/nfldata mirror — third-party, NOT official"
WIN = 100.0 / 110.0  # profit per unit staked at -110
BE = 110.0 / 210.0   # break-even hit rate at -110


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def main() -> int:
    def norm_gid(gid: str) -> str:
        return gid.replace("_LAR", "_LA").replace("_ARI", "_AZ")

    results = {}
    with open(os.path.join(OUT, "verified_results_2026.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            results[norm_gid(r["game_id"])] = r

    modeled = []
    with open(os.path.join(ROOT, "data", "processed", "games_modeled.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["season"] == "2026" and norm_gid(r["game_id"]) in results and r["model_spread"]:
                modeled.append(r)
    if len(modeled) != len(results):
        print(f"note: {len(modeled)} modeled of {len(results)} verified games")

    bets: list[dict] = []

    def add_bet(m: dict, strategy: str, market: str, side: str, line: float) -> None:
        res = results[norm_gid(m["game_id"])]
        as_, hs = int(res["away_score"]), int(res["home_score"])
        if market == "spread":
            # home covers if home margin exceeds the home-favoured line
            margin = hs - as_
            if margin == line:
                outcome = "push"
            elif (side == "home" and margin > line) or (side == "away" and margin < line):
                outcome = "win"
            else:
                outcome = "loss"
        else:
            total = hs + as_
            if total == line:
                outcome = "push"
            elif (side == "over" and total > line) or (side == "under" and total < line):
                outcome = "win"
            else:
                outcome = "loss"
        profit = {"win": WIN, "loss": -1.0, "push": 0.0}[outcome]
        bets.append({
            "strategy": strategy, "market": market, "side": side,
            "line": f"{line:g}", "game_id": res["game_id"],
            "date": res["date_iso"],
            "away_team": res["away_team"], "away_score": as_,
            "home_team": res["home_team"], "home_score": hs,
            "outcome": outcome, "profit": f"{profit:.4f}",
            "price": "-110", "price_source": PRICE_NOTE,
            "line_source": MODEL_NOTE if strategy.startswith("MODEL") else MIRROR_NOTE,
            "outcome_source": res["source_url"],
            "results_feed": "data/results/verified_results_2026.csv",
        })

    for m in modeled:
        ms, mk = float(m["model_spread"]), float(m["market_spread"])
        mt, mkt = float(m["model_total"]), float(m["market_total"])
        for t in (1, 3, 5):
            if abs(ms - mk) >= t:
                side = "home" if ms > mk else "away"
                add_bet(m, f"MODEL_SIDE_{t}", "spread", side, mk)
            if abs(mt - mkt) >= t:
                side = "over" if mt > mkt else "under"
                add_bet(m, f"MODEL_TOTAL_{t}", "total", side, mkt)
        add_bet(m, "BASE_HOME_ATS", "spread", "home", float(m["market_spread"]))
        add_bet(m, "BASE_OVER", "total", "over", float(m["market_total"]))

    # ------------------------------------------------------------ write bets
    cols = ["strategy", "market", "side", "line", "game_id", "date", "away_team",
            "away_score", "home_team", "home_score", "outcome", "profit", "price",
            "price_source", "line_source", "outcome_source", "results_feed"]
    with open(os.path.join(OUT, "graded_bets.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(bets)

    # -------------------------------------------------------------- summary
    by_strat: dict[str, list[dict]] = defaultdict(list)
    for b in bets:
        by_strat[b["strategy"]].append(b)

    rows = []
    for strat in sorted(by_strat):
        bs = by_strat[strat]
        n = len(bs)
        wins = sum(1 for b in bs if b["outcome"] == "win")
        losses = sum(1 for b in bs if b["outcome"] == "loss")
        pushes = n - wins - losses
        units = sum(float(b["profit"]) for b in bs)
        roi = units / n * 100 if n else 0.0
        lo, hi = wilson(wins, n)
        hit = wins / n * 100 if n else 0.0
        z = (wins / n - BE) / math.sqrt(BE * (1 - BE) / n) if n else 0.0
        rows.append({
            "strategy": strat,
            "bets": n, "wins": wins, "losses": losses, "pushes": pushes,
            "hit_rate_pct": f"{hit:.2f}",
            "hit_ci95_lo_pct": f"{lo * 100:.2f}", "hit_ci95_hi_pct": f"{hi * 100:.2f}",
            "roi_at_assumed_minus110_pct": f"{roi:.2f}",
            "units": f"{units:.3f}",
            "z_vs_breakeven": f"{z:.2f}",
            "breakeven_hit_pct": f"{BE * 100:.2f}",
            "price_basis": PRICE_NOTE,
            "outcome_basis": "official verified results feed (nfl.com)",
        })

    # model accuracy vs verified outcomes (no prices involved)
    errs_s, errs_t = [], []
    for m in modeled:
        res = results[norm_gid(m["game_id"])]
        margin = int(res["home_score"]) - int(res["away_score"])
        total = int(res["home_score"]) + int(res["away_score"])
        errs_s.append(abs(float(m["model_spread"]) - margin))
        errs_t.append(abs(float(m["model_total"]) - total))
    acc = {
        "strategy": "MODEL_ACCURACY_VS_VERIFIED (no price involved)",
        "bets": len(modeled), "wins": "", "losses": "", "pushes": "",
        "hit_rate_pct": "", "hit_ci95_lo_pct": "", "hit_ci95_hi_pct": "",
        "roi_at_assumed_minus110_pct": "",
        "units": "",
        "z_vs_breakeven": "",
        "breakeven_hit_pct": "",
        "price_basis": "n/a — accuracy statistic, not a bet",
        "outcome_basis": f"official verified results feed; spread MAE {sum(errs_s) / len(errs_s):.2f} pts, total MAE {sum(errs_t) / len(errs_t):.2f} pts over {len(errs_s)} games",
    }

    scols = ["strategy", "bets", "wins", "losses", "pushes", "hit_rate_pct",
             "hit_ci95_lo_pct", "hit_ci95_hi_pct", "roi_at_assumed_minus110_pct",
             "units", "z_vs_breakeven", "breakeven_hit_pct", "price_basis", "outcome_basis"]
    with open(os.path.join(OUT, "roi_summary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=scols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
        w.writerow(acc)

    print(f"graded bets        : {len(bets)} over {len(modeled)} verified games")
    for r in rows:
        print(f"  {r['strategy']:<16} n={r['bets']:>3} hit={r['hit_rate_pct']:>6}% "
              f"roi={r['roi_at_assumed_minus110_pct']:>7}% z={r['z_vs_breakeven']}")
    print(f"  MODEL ACCURACY   spread MAE {sum(errs_s) / len(errs_s):.2f}  "
          f"total MAE {sum(errs_t) / len(errs_t):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
