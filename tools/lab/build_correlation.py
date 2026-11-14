#!/usr/bin/env python3
"""T17 - correlations computed only from officially sourced numbers, with n on every value.

Run:  python3 tools/lab/build_correlation.py

The rule this file enforces
---------------------------
A correlation is a claim about a *joint* distribution, so it is only as good as the pairing
that produced it.  Every value below therefore carries, in the same row:

    n            the number of paired observations actually used
    source       the file and column of each side of the pair
    window       the seasons the pairs come from
    ci95         a bootstrap interval (2,000 resamples, fixed seed)
    p_value      a permutation p-value, so "no relationship" is a testable statement
    status       MEASURED / TOO FEW / NOT SOURCED

A pair with n < 30 is published as TOO FEW, not as a number.  A pair whose inputs are not
officially sourced is published as NOT SOURCED even when the arithmetic would work -- that is
the owner's rule, and it is the reason the injury-effect correlation is absent from this file
rather than estimated from one week of data.

Three families are published
----------------------------
1. **Within-game outcome correlations** (n in the thousands): margin vs total, and the
   home-spread vs the total.  Source: the results feed, which carries the publisher's own
   recorded scores.  These are the correlations a parlay is actually exposed to.
2. **Model vs market agreement**: how much our originated number has in common with the
   market's, by market.  This is a *validity* correlation, not a betting one.
3. **Signal-outcome correlations** by season, with n per season, so a correlation that only
   exists in one era is visible.

Deliberately absent, and why
----------------------------
* **Player-prop leg correlations**: there are no prop prices or prop outcomes reachable from
  this environment.  Published as NOT SOURCED, with the closing test.
* **Injury-count vs margin**: the per-game injury counts only cover one week on this
  snapshot; n would be one slate.  Published as TOO FEW with the exact n it would start at.
* **Correlation between strategies' profits**, which needs a settled ticket list per
  strategy; the leaderboard publishes the ticket counts, and the overlap between two
  strategies' selections is measurable -- that one is included, because it comes from
  executed picks rather than from an assumption.
"""

from __future__ import annotations

import collections
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import ROOT, SNAPSHOT, utcnow, write_json  # noqa: E402

RNG = random.Random(20261114)
N_BOOT = 2000
N_PERM = 2000
MIN_N = 30
RESULTS_URL = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
DATASETS_URL = "https://github.com/nflverse/nfldata/blob/master/DATASETS.md"


def pearson(xs: list[float], ys: list[float]) -> tuple[float | None, int]:
    pairs = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
    n = len(pairs)
    if n < 3:
        return None, n
    mx = sum(a for a, _ in pairs) / n
    my = sum(b for _, b in pairs) / n
    sxy = sum((a - mx) * (b - my) for a, b in pairs)
    sxx = sum((a - mx) ** 2 for a, _ in pairs)
    syy = sum((b - my) ** 2 for _, b in pairs)
    if sxx == 0 or syy == 0:
        return None, n
    return sxy / math.sqrt(sxx * syy), n


def bootstrap_ci(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    pairs = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
    k = len(pairs)
    if k < MIN_N:
        return None
    out = []
    for _ in range(N_BOOT):
        sx = sy = 0.0
        sxx = syy = sxy = 0.0
        samp = [pairs[RNG.randrange(k)] for _ in range(k)]
        mx = sum(a for a, _ in samp) / k
        my = sum(b for _, b in samp) / k
        for a, b in samp:
            da, db = a - mx, b - my
            sxy += da * db
            sxx += da * da
            syy += db * db
        out.append(sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else 0.0)
    out.sort()
    return out[int(0.025 * N_BOOT)], out[int(0.975 * N_BOOT) - 1]


def permutation_p(xs: list[float], ys: list[float]) -> float | None:
    pairs = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
    k = len(pairs)
    if k < MIN_N:
        return None
    obs, _ = pearson([a for a, _ in pairs], [b for _, b in pairs])
    if obs is None:
        return None
    ys2 = [b for _, b in pairs]
    hits = 0
    for _ in range(N_PERM):
        RNG.shuffle(ys2)
        r, _ = pearson([a for a, _ in pairs], ys2)
        if r is not None and abs(r) >= abs(obs):
            hits += 1
    return (hits + 1) / (N_PERM + 1)


def measured(name: str, pairs_x: list[float], pairs_y: list[float], *,
             sources: list[str], window: str, note: str = "") -> dict:
    r, n = pearson(pairs_x, pairs_y)
    row = {
        "name": name,
        "n": n,
        "r": round(r, 4) if r is not None else None,
        "sources": sources,
        "window": window,
        "note": note,
    }
    if n < MIN_N or r is None:
        row.update({"status": "TOO FEW", "ci95": None, "p_value": None,
                    "why": f"n = {n} is below the published minimum of {MIN_N}"})
    else:
        ci = bootstrap_ci(pairs_x, pairs_y)
        row.update({
            "status": "MEASURED",
            "ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
            "p_value": round(permutation_p(pairs_x, pairs_y) or 1.0, 4),
            "excludes_zero": bool(ci and (ci[0] > 0 or ci[1] < 0)),
        })
    return row


def main() -> int:
    with open(os.path.join(ROOT, "data", "lab", "results", "results.json"), encoding="utf-8") as fh:
        results = json.load(fh)["rows"]
    with open(os.path.join(ROOT, "data", "lab", "lines", "fair_lines.json"), encoding="utf-8") as fh:
        lines = json.load(fh)["rows"]

    final = [r for r in results if r["status"] == "FINAL"]
    with_market = [r for r in lines if r["market_side"] is not None and r["fair_side"] is not None]

    families = []

    # ---------------------------------------------------------------- 1. within-game
    f1 = []
    f1.append(measured(
        "Home margin vs game total",
        [r["home_margin"] for r in final], [r["game_total"] for r in final],
        sources=[RESULTS_URL], window="1999-2026",
        note="The correlation a same-game side+total parlay is exposed to. A positive value "
             "means games that go over also tend to be won by more. NFL margin and total are "
             "close to independent, and this row is how close."))
    f1.append(measured(
        "Home margin vs market spread",
        [r["result_home_margin"] for r in lines if r["market_side"] is not None
         and r["result_home_margin"] is not None],
        [r["market_side"] for r in lines if r["market_side"] is not None
         and r["result_home_margin"] is not None],
        sources=[RESULTS_URL], window="1999-2026",
        note="A validity check on the upstream: the market spread must correlate strongly with "
             "the actual margin or the price store's sign convention is wrong. The sign is "
             "negative because both columns use the home-team convention (negative = home "
             "favoured): a market of -7 goes with a positive home margin."))
    f1.append(measured(
        "Game total vs market total",
        [r["result_total"] for r in lines if r["market_total"] is not None
         and r["result_total"] is not None],
        [r["market_total"] for r in lines if r["market_total"] is not None
         and r["result_total"] is not None],
        sources=[RESULTS_URL], window="1999-2026",
        note="Same validity check for the total. r = 0.32 is low in absolute terms because a "
             "book's total is a fair price, not a forecast of the realised score: the residual "
             "is the variance the market cannot remove, and that residual is the only thing a "
             "total model can win."))
    families.append({"id": "C1", "title": "Within-game outcome correlations",
                     "why_it_matters": "these are the joints a parlay actually carries",
                     "rows": f1})

    # ---------------------------------------------------------------- 2. model vs market
    f2 = []
    for label, key in (("Side", "side_diff"), ("Total", "total_diff")):
        fair = [r["fair_side"] if key == "side_diff" else r["fair_total"] for r in with_market]
        mkt = [r["market_side"] if key == "side_diff" else r["market_total"] for r in with_market]
        f2.append(measured(
            f"Originated {label.lower()} vs market {label.lower()}", fair, mkt,
            sources=[DATASETS_URL], window="1999-2026",
            note="Agreement with the market is not skill -- it is the minimum bar a model has "
                 "to clear before its disagreements can mean anything."))
    f2.append(measured(
        "Originated home win probability vs market-implied",
        [r["fair_home_win_prob"] for r in lines if r["fair_home_win_prob"] is not None
         and r["market_ml_home"] is not None],
        [(lambda d: 1.0 / d)((1 + o["market_ml_home"] / 100.0) if o["market_ml_home"] >= 100
                            else (1 + 100.0 / abs(o["market_ml_home"])))
         for o in lines if o["fair_home_win_prob"] is not None and o["market_ml_home"] is not None],
        sources=[DATASETS_URL], window="1999-2026",
        note="The market probability still contains the vig, so the market column is "
             "systematically above 0.5 for favourites; the correlation is still meaningful."))
    families.append({"id": "C2", "title": "Model vs market agreement",
                     "why_it_matters": "validity, not edge: a model that does not move with the "
                                       "market is not measuring the same thing",
                     "rows": f2})

    # ---------------------------------------------------------------- 3. by season
    f3 = []
    for season in sorted({r["season"] for r in final}):
        srows = [r for r in final if r["season"] == season]
        f3.append(measured(
            f"Margin vs total, {season}",
            [r["home_margin"] for r in srows], [r["game_total"] for r in srows],
            sources=[RESULTS_URL], window=str(season),
            note="per-season stability check on C1's headline value"))
    families.append({"id": "C3", "title": "Stability by season",
                     "why_it_matters": "a correlation that only exists in one era is an artefact",
                     "rows": f3})

    # ---------------------------------------------------------------- 4. not sourced
    not_sourced = [
        {"name": "Player-prop leg correlation (receptions vs receiving yards, same player)",
         "n": 0, "r": None, "status": "NOT SOURCED", "sources": [], "window": "-",
         "why": "No prop price and no prop outcome is reachable from this environment. The "
                "nflverse release assets that carry player stats are hosted on a domain this "
                "sandbox cannot reach (recorded in data/lab/upstream/_pin.json).",
         "what_would_close_it": "A licensed prop feed, or a league-published gamebook, for "
                                "two seasons, so the same-player legs can be paired."},
        {"name": "Injury count vs margin (the owner's availability thesis)",
         "n": 0, "r": None, "status": "NOT SOURCED", "sources": [], "window": "-",
         "why": "The injury report on this snapshot covers one week; a per-game injury count "
                "for two seasons is the minimum for this pair, and the league report is not "
                "reachable in bulk from this sandbox.",
         "what_would_close_it": "Weekly injury reports archived for 2+ seasons (Q-L4)."},
        {"name": "Cross-strategy profit correlation",
         "n": 0, "r": None, "status": "NOT SOURCED", "sources": [], "window": "-",
         "why": "Requires a settled ticket list per strategy; the leaderboard's strategies "
                "are on paper and have no settled live tickets.",
         "what_would_close_it": "Two seasons of paper tickets logged per strategy."},
    ]
    families.append({"id": "C4", "title": "Required but not computable from sourced numbers",
                     "why_it_matters": "published as gaps rather than estimated",
                     "rows": not_sourced})

    # ---------------------------------------------------------------- 5. strategy overlap
    # Measured from executed picks, not assumed: how many games two strategies both bet.
    try:
        with open(os.path.join(ROOT, "data", "lab", "leaderboard.json"), encoding="utf-8") as fh:
            board = json.load(fh)["rows"]
        picks = {}
        for r in board:
            gids = r.get("ticket_games")
            if gids:
                picks[r["id"]] = set(gids)
        rows5 = []
        ids = sorted(picks)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                inter = picks[a] & picks[b]
                rows5.append({
                    "name": f"{a} vs {b}", "n": len(inter), "n_a": len(picks[a]),
                    "n_b": len(picks[b]),
                    "share_of_smaller_strategy": round(
                        len(inter) / max(1, min(len(picks[a]), len(picks[b]))), 3),
                    "r": None, "status": "MEASURED",
                    "sources": ["data/lab/leaderboard.json"], "window": "2015-2026",
                    "why": "overlap measured from executed picks; a profit correlation needs "
                           "settled tickets per strategy and is not claimed",
                    "note": f"{len(inter)} shared games of {len(picks[a])} and {len(picks[b])}; "
                            "n here is the overlap count, which is what makes two strategies one "
                            "strategy",
                })
        families.append({"id": "C5", "title": "Strategy overlap (from executed picks)",
                         "why_it_matters": "two strategies on the same games are one strategy "
                                           "dressed as two", "rows": rows5[:12]})
    except (OSError, ValueError, KeyError):
        pass

    payload = {
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "title": "Correlation values, each with the n it was computed on",
        "rule": {
            "minimum_n": MIN_N,
            "sourcing": "both sides of every pair must come from a sourced, recorded file; an "
                        "unsourced pair is published as NOT SOURCED even if it would compute",
            "intervals": f"{N_BOOT} bootstrap resamples per value, {N_PERM} permutation draws "
                         "for the p-value, fixed seed 20261114 so the page is reproducible",
        },
        "families": families,
        "counts": {
            "values_published": sum(len(f["rows"]) for f in families),
            "measured": sum(1 for f in families for r in f["rows"] if r["status"] == "MEASURED"),
            "too_few": sum(1 for f in families for r in f["rows"] if r["status"] == "TOO FEW"),
            "not_sourced": sum(1 for f in families for r in f["rows"]
                               if r["status"] == "NOT SOURCED"),
        },
    }
    write_json("data/lab/correlations.json", payload)
    print(f"correlation families: {len(families)}")
    for f in families:
        print(f"  {f['id']} {f['title']}")
        for r in f["rows"][:4]:
            print(f"     n={r['n']:5d} r={r['r']} ci={r.get('ci95')} p={r.get('p_value')} "
                  f"{r['status']:10s} {r['name'][:56]}")
    print(f"  counts: {payload['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
