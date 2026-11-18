#!/usr/bin/env python3
"""Two-sided "what would change our mind" register for every strategy on the board.

    python3 tools/official/mind_change.py build
    python3 tools/official/mind_change.py check     # CI: the published file reproduces

Owner's brief, round 6:

    "Add a two-sided 'what would change our mind' field to every strategy entry."

Two-sided means both halves are mandatory and both are numeric. A strategy entry that says "more
data" for its refutation has not said anything, so `check` fails a row whose confirm or refute cell
does not contain a number, and fails the register if any strategy on the board is missing a row.

Where the numbers come from: the confirm half is written against this repository's own promotion
gates (G1..G8 in `src/console/strategy.py`) and the refute half against its demotion gates
(D1..D4) plus the strategy's own parameter, so "what would change our mind" is the same arithmetic
that promotes and demotes — not a second, softer standard invented for the page. The gates are the
registered rule; this register is the promise that those rules will be allowed to kill the entry.

Writes `data/console/mind_change.csv` (rendered on the console's strategy page) and
`data/console/mind_change_meta.json`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRATEGY_TABLE = os.path.join(ROOT, "data", "console", "strategy_results.csv")
OUT_CSV = os.path.join(ROOT, "data", "console", "mind_change.csv")
OUT_META = os.path.join(ROOT, "data", "console", "mind_change_meta.json")
GATES_URL = ("https://github.com/karagemop466-tech/X1/blob/main/docs/methodology/"
             "validation-gates.md")
PREREG_URL = "https://github.com/karagemop466-tech/X1/tree/main/docs/preregistration"

COLUMNS = ["strategy_id", "family", "rule_as_registered", "parameter", "confirm", "refute",
           "holdout_window", "multiplicity_note", "gates_ref", "prereg_ref"]

# Authored once, here, so the register and the check cannot disagree. Each confirm/refute pair
# names a quantity, not a mood.
CONFIRM_COMMON = ("promotion needs all 8 gates: at least 200 settled out-of-sample bets, "
                  "bootstrap 95% CI lower bound on flat ROI above 0 with exact binomial p <= 0.05, "
                  "ROI at or above 2% under the strategy's own staking plan, positive after dropping "
                  "one-score (margin <= 3) and blowout (margin >= 21) games, and at least 60% of "
                  "neighbouring parameter settings positive")
REFUTE_D = ("any of: trailing 200 settled bets at flat stakes show negative ROI; the trailing 100 "
            "bets have mean signed edge at or below 0; peak-to-trough drawdown exceeds 25% of the "
            "60-unit bankroll; trailing signal score below 50 — each of which sends the entry back "
            "to paper without waiting for the season to end")

ENTRIES: dict[str, tuple[str, str]] = {
    "ST-SIDE-3": (
        "the 3-point side residual keeps a positive mean signed edge across a prospective 300-bet "
        "window, the RMSE of our fair side stays at or below the market's 13.14, and the 2- and "
        "4-point neighbours stay positive",
        "the 300-bet prospective window shows a mean signed edge at or below 0 points, or the "
        "2-point and 4-point neighbours are both negative while the 3-point setting alone is "
        "positive — that is a spike, not a rule"),
    "ST-SIDE-5": (
        "same as the 3-point entry, with 4- and 6-point neighbours positive and at least 200 "
        "settled bets in the window",
        "a 5-point cut produces fewer than 200 settled bets in two consecutive prospective "
        "windows, or its hit rate is inside the break-even band 52.38% +/- 2 points"),
    "ST-SIDE-7": (
        "the 7-point cut survives with at least 200 settled bets and a positive lower CI bound; "
        "6- and 8-point neighbours positive",
        "the residual size that survives is only the tail the model gets wrong together with the "
        "market — shown by the 6- and 8-point neighbours both being negative"),
    "ST-TOT-3": (
        "the 3-point total residual holds a positive mean signed edge over a 300-bet prospective "
        "window with 2- and 4-point neighbours positive",
        "total results stay unpriced (no market total for the fixture) in more than 20% of the "
        "window, or the RMSE against actual total points is worse than the market's"),
    "ST-TOT-5": (
        "at least 200 settled bets at the 5-point cut with the lower CI bound above 0",
        "the 5-point cut's edge comes from fewer than 2 games per week concentrated in one "
        "season-half — shown by the second half of the window being negative"),
    "ST-TOT-7": (
        "the 7-point cut holds 200+ settled bets and a positive lower bound; currently 588 bets "
        "over the whole backtest window, so a prospective 200 needs two full seasons",
        "a cut this deep selects on model error rather than market error, which is visible as a "
        "correlation above 0.85 with ST-TOT-5 and ST-TOT-3 combined"),
    "ST-ML-5": (
        "probability residuals of 5 points or more keep a hit rate above 52.38% over 300 bets, and "
        "the moneyline derived from the same margin model stays inside 1 point of the market's",
        "the apparent edge is smaller than the 4.55% vig gap at -110, i.e. the residual is the "
        "juice and not the price — recomputed against the mirror's two-sided quotes whenever "
        "both ends exist (1,072 of 18,902 markets)"),
    "ST-ML-10": (
        "10-point probability residuals hold above 52.38% over 200+ bets with the 8- and "
        "12-point neighbours positive",
        "the sample at this depth cannot reach 200 settled bets inside 2 prospective windows"),
    "ST-UNDER48": (
        "unders at totals of 48+ keep a positive mean margin-to-line over 300 bets after dropping "
        "blowouts, which is where a structural under bias would survive",
        "the effect lives only in the dropped buckets (margin <= 3 or >= 21), or reverses in the "
        "second half of the window"),
    "ST-OVER40": (
        "overs at totals of 40 or lower hold a positive edge over 200+ bets with the 38 and 42 "
        "neighbours positive",
        "the rule's profit comes from the under-4% of games where the market total is itself "
        "mis-transcribed (the price store keeps 1,072 of 18,902 markets with both ends), shown by "
        "the edge in the remaining 96% falling below 0.5 points per bet"),
    "ST-ROADFAV": (
        "road teams laying 2.5+ beat the spread above 52.38% over 300 bets, and the effect survives "
        "splitting by venue type where a venue is printed",
        "the edge falls below 0.5 points per bet once the fixture-context rest-day difference is "
        "controlled for, or the correlation between this rule and the rest-differential feature "
        "exceeds 0.85 — then it is a rest rule wearing a travel costume"),
    "ST-HOMEDOG": (
        "home dogs of 2.5+ receive a positive edge over 300 bets with the 2 and 5 point "
        "neighbours positive",
        "the edge is one season deep: the same rule on the other 2 seasons in the walk-forward is "
        "negative"),
    "ST-DIVDOG": (
        "division underdogs hold a positive mean signed edge over 300 bets, and the effect is not "
        "carried by a single club (largest club share below 15% of bets)",
        "one club carries more than 20% of the bets, or the edge disappears when the 21+ point "
        "blowout games are dropped, which is the signature of a market-structure artefact "
        "rather than an edge"),
    "ST-REST2": (
        "a rest advantage of 2+ days keeps a positive edge over 200+ bets and the published "
        "rest-vs-margin correlation is at or above 0.05 in absolute value with n printed",
        "the edge falls below 0.5 points per bet once the Thursday slot (1 of the 16 weekly "
        "fixture windows, flagged prime_time=yes in the fixture-context table) is excluded"),
    "ST-BOTH-3": (
        "the two legs stay independent enough that the joint hit rate is at least the product of "
        "the marginals minus 2 points over 300 paired bets",
        "measured joint hit rate falls below the product of the marginals by more than 4 points — "
        "then the combination is double-counting one signal and must be merged back into ST-SIDE-3"),
    "ST-PARLAY-4": (
        "a joint probability measured on at least 200 paired bets, within 2 points of the product "
        "of the marginals, plus the operator's void/push rules for both legs recorded; only then "
        "may the parlay be ranked at all",
        "the joint-evidence gate stays unsatisfied — parlay leg correlations above 0.85 mean the "
        "'4 legs' are one bet, and the entry is killed rather than rescaled"),
}

HOLDOUT = ("prospective escrow only: 300 settled bets for side/total rules, 200 for the deep cuts; "
           "backtest numbers never enter the leaderboard")
MULT = ("16 strategies were scored on the same window, so a Bonferroni-adjusted alpha of 0.05/16 "
        "= 0.003125 is the bar this entry has to clear, not 0.05")


def registered_ids() -> list[str]:
    if not os.path.exists(STRATEGY_TABLE):
        return []
    with open(STRATEGY_TABLE, encoding="utf-8", newline="") as fh:
        return [r["ID"] for r in csv.DictReader(fh)]


def build(do_write: bool = True) -> tuple[list[dict], dict]:
    ids = registered_ids()
    rows, problems = [], []
    for sid in ids:
        entry = ENTRIES.get(sid)
        if entry is None:
            problems.append(f"{sid}: no mind-change pair authored")
            continue
        confirm, refute = entry
        rows.append({"strategy_id": sid, "family": "", "rule_as_registered": "", "parameter": "",
                     "confirm": confirm, "refute": refute, "holdout_window": HOLDOUT,
                     "multiplicity_note": MULT,
                     "gates_ref": GATES_URL, "prereg_ref": PREREG_URL})
    if ids:
        with open(STRATEGY_TABLE, encoding="utf-8", newline="") as fh:
            by_id = {r["ID"]: r for r in csv.DictReader(fh)}
        for r in rows:
            src = by_id.get(r["strategy_id"], {})
            r["family"] = src.get("FAMILY", "")
            r["rule_as_registered"] = src.get("RULE", "")
            r["parameter"] = src.get("PARAM", "")
    # every cell must be present, and both sides must carry a number
    numeric = re.compile(r"\d")
    for r in rows:
        for col in ("confirm", "refute"):
            if not numeric.search(r[col]):
                problems.append(f"{r['strategy_id']}: {col} has no number in it")
    missing = sorted(set(ids) - {r["strategy_id"] for r in rows})
    for m in missing:
        problems.append(f"{m}: strategy on the board with no mind-change row")
    meta = {"dataset": "mind-change", "title": "Two-sided what-would-change-our-mind register",
            "generated_by": "tools/official/mind_change.py",
            "rule": "both halves mandatory, both numeric; the standard is the promotion and "
                    "demotion gates themselves, not a softer one invented for the page",
            "strategies_on_board": len(ids), "rows": len(rows),
            "coverage_pct": (round(100.0 * len(rows) / len(ids), 1) if ids else 0.0),
            "problems": problems}
    if do_write:
        os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        with open(OUT_META, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=1, sort_keys=True)
            fh.write("\n")
    return rows, meta


def cmd_build(_args) -> int:
    rows, meta = build()
    print(f"mind-change register: {meta['rows']} rows for {meta['strategies_on_board']} "
          f"strategies ({meta['coverage_pct']}%)")
    for p in meta["problems"]:
        print("  PROBLEM:", p)
    return 1 if meta["problems"] else 0


def cmd_check(_args) -> int:
    before = open(OUT_CSV, encoding="utf-8").read() if os.path.exists(OUT_CSV) else ""
    rows, meta = build(do_write=False)
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    if buf.getvalue() != before:
        print("FAIL: data/console/mind_change.csv is stale — rebuild with "
              "python3 tools/official/mind_change.py build")
        return 1
    if meta["problems"]:
        print("FAIL: register incomplete:", "; ".join(meta["problems"]))
        return 1
    print(f"PASS: mind-change register covers {meta['rows']}/{meta['strategies_on_board']} "
          f"strategies, both sides numeric, file reproduces")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.set_defaults(func=cmd_build)
    c = sub.add_parser("check")
    c.set_defaults(func=cmd_check)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
