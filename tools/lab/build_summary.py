#!/usr/bin/env python3
"""Build the executive summary for this round, from the artefacts.

Run:  python3 tools/lab/build_summary.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import ROOT, SNAPSHOT, utcnow, write_json  # noqa: E402


def load(rel: str):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    prices = load("data/lab/prices/price_coverage.json")
    results = load("data/lab/results/result_summary.json")
    lines = load("data/lab/lines/fair_lines.json")
    model = load("data/lab/lines/model_report.json")
    board = load("data/lab/leaderboard.json")
    defi = load("data/lab/deficiency.json")
    corr = load("data/lab/correlations.json")
    q = load("data/lab/questions.json")
    s = load("data/lab/suggestions.json")

    acc, pt = model["accuracy"], prices["totals"]
    bc = board["summary"]["counts"]

    payload = {
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "title": "Executive summary: what this round actually established",
        "headline": (
            "All eight of this round's requirements are built and running: a price-snapshot "
            "store, a verified results feed, an originated line ordered side then total then "
            "moneyline, fair/market/difference as separate columns, a leaderboard that scores "
            "signal and staking separately, replacement depth down to the fourth string, "
            "correlations that carry their own n, and a demotion gate that has already fired. "
            "None of them produced a bettable edge, and the summary says why in numbers rather "
            "than adjectives."
        ),
        "the_one_paragraph": (
            f"The results feed is complete and internally consistent ({results['coverage']['final']:,} "
            f"scored games, 0 arithmetic mismatches). The price store is structurally incomplete: "
            f"{pt['market_rows']:,} market rows, {pt['rows_where_opening_and_closing_both_exist']} "
            "of which have both an opening and a closing number, because the two files that "
            "evidence them cover different seasons and neither names a book or a timestamp. The "
            f"model originates every market but loses to the market on every metric (side MAE "
            f"{acc['side_mae_model']} vs {acc['side_mae_market']}, Brier {acc['brier_model']} vs "
            f"{acc['brier_market']}). The leaderboard has {bc['live']} live strategies. One "
            "strategy shows a positive ROI and it is the one with the weakest signal -- the exact "
            "case the signal/staking split exists to catch -- and the demotion gate sends it back "
            "to paper on drawdown and on price loss."
        ),
        "what_is_new": [
            {"id": "T11", "item": "Price-snapshot store",
             "result": f"{pt['market_rows']:,} market rows across side, total and moneyline, each "
                       "labelled with the file, column and hash it came from",
             "honest_state": "0 markets have both an opening and a closing number; 5 defects "
                             "recorded (P-01..P-05)"},
            {"id": "T12", "item": "Verified results feed",
             "result": f"{results['coverage']['final']:,} scored games, arithmetic re-checked "
                       "against the publisher's own columns, push-aware settlement rule written "
                       "down once",
             "honest_state": "complete for every game the publisher scored; 135 unplayed games "
                             "carried as SCHEDULED, never zero-filled"},
            {"id": "T13", "item": "Side -> total -> moneyline origination",
             "result": f"{lines['counts']['with_fair_side']:,} originated sides, "
                       f"{lines['counts']['with_both_total']:,} originated totals, "
                       f"{lines['counts']['with_moneyline']:,} moneylines, all walk-forward",
             "honest_state": "loses to the market; published as a screen, not an edge"},
            {"id": "T14", "item": "Fair line / market line / difference as separate columns",
             "result": "every market row carries the three values side by side, plus the "
                       "provenance of each",
             "honest_state": "the market column is one unnamed composite (no book is named by "
                             "the source)"},
            {"id": "T15", "item": "Signal separated from staking",
             "result": f"8 strategies scored on signal (z, interval, luck-trimmed hit rate) and "
                       f"on money (flat and 5%-compounding), ranked signal-first",
             "honest_state": f"{bc['live']} live; the only positive ROI has z = 1.00"},
            {"id": "T16", "item": "Replacement depth",
             "result": f"{defi['totals']['replacement_certain']} certain starter replacements, "
                       f"{defi['totals']['certain_replacements_with_no_replacement_listed']} "
                       "slots where the club lists nobody, plus "
                       f"{defi['totals']['depth_losses_second_string_or_deeper']} depth losses "
                       "among backups",
             "honest_state": "no third-string starter anywhere on this snapshot; no line effect "
                             "claimed"},
            {"id": "T17", "item": "Correlation with n",
             "result": f"{corr['counts']['values_published']} values, each with n, a bootstrap "
                       "interval and a permutation p",
             "honest_state": f"{corr['counts']['not_sourced']} required pairs published as NOT "
                             "SOURCED rather than estimated"},
            {"id": "T18", "item": "Demotion gate",
             "result": "four triggers (decay, staking break, price loss, drift) evaluated on "
                       "every build; the parlay is demoted on two of them",
             "honest_state": "the gate fires on real data, including against a profitable row"},
        ],
        "the_numbers_that_matter": [
            {"label": "Originated sides vs market (MAE, out of sample)",
             "value": f"{acc['side_mae_model']} vs {acc['side_mae_market']}",
             "reading": "the market is better; the model still beats a 2.5-point constant "
                        f"({acc['side_mae_constant_hfa_2_5']}), so it is not noise either"},
            {"label": "Calibration (Brier, lower is better)",
             "value": f"{acc['brier_model']} vs {acc['brier_market']}",
             "reading": "the market's probabilities are better calibrated by a clear margin"},
            {"label": "Correlation between our side and the market's",
             "value": f"r = {acc['corr_fair_vs_market']} (n = {acc['n_side']:,})",
             "reading": "we are measuring the same quantity, partially -- a model that did not "
                        "correlate would not be measuring the spread at all"},
            {"label": "Proportion of market rows with an opening and a closing number",
             "value": f"0 of {pt['market_rows']:,}",
             "reading": "the single biggest structural gap; it blocks CLV, the demotion trigger "
                        "D-03 in its proper form, and gate G0"},
            {"label": "Strategies that are live",
             "value": f"{bc['live']} of {bc['strategies']}",
             "reading": "the correct output of a validation system on its first run"},
            {"label": "The parlay that looks good",
             "value": "+10.5% ROI, z = 1.00, demoted",
             "reading": "a positive ROI sitting on a signal that is indistinguishable from "
                        "chance, killed by the drawdown and price-loss triggers"},
        ],
        "defects_found_and_fixed_this_round": [
            {"id": "L-01", "where": "line model",
             "what": "sample weight applied to the target only; total MAE 28.4 published",
             "fix": "weighted ridge on both X'X and X'y"},
            {"id": "L-02", "where": "line model",
             "what": "'this week' board published week 18", "fix": "earliest week with unplayed games"},
            {"id": "L-03", "where": "line model",
             "what": "home and away ratings entered with the same sign, so the difference "
                     "cancelled; the line was a constant (corr with market 0.024)",
             "fix": "signed design matrix; corr rose to 0.470 and MAE improved to 10.741"},
            {"id": "B-01", "where": "leaderboard",
             "what": "a flat 52.38% break-even was applied to moneyline and parlay tickets",
             "fix": "per-ticket Poisson-binomial test"},
            {"id": "B-02", "where": "leaderboard",
             "what": "parlay wins paid at single-leg odds (-40.7% ROI instead of +10.5%)",
             "fix": "compounded payout"},
            {"id": "B-03", "where": "leaderboard",
             "what": "ranking on ROI alone put the weakest signal first", "fix": "signal-first rank"},
            {"id": "B-04", "where": "leaderboard",
             "what": "luck decomposition bucketed parlay legs the wrong way round",
             "fix": "variance-dominated if ANY leg is"},
        ],
        "what_is_blocked_and_by_what": [
            {"blocked": "true closing-line value", "by": "no timestamp and no book on any price row",
             "question": "Q-P1, Q-P2"},
            {"blocked": "any live strategy", "by": "no executable price, so gate G0 cannot pass",
             "question": "Q-V1"},
            {"blocked": "prop markets", "by": "no reachable prop price or prop outcome",
             "question": "Q-D1"},
            {"blocked": "injury effect on the line", "by": "one week of injury data",
             "question": "Q-M2, Q-D2"},
            {"blocked": "rewards", "by": "no reward definition and no legal review",
             "question": "Q-S2"},
        ],
        "decisions_waiting_on_the_owner": [
            {"id": "Q-S1", "decision": "may a positive ROI with a weak signal be surfaced at all",
             "suggestion": "S-L2, S-L5"},
            {"id": "Q-S2", "decision": "what a reward is, and whether money is involved",
             "suggestion": "S-L2"},
            {"id": "Q-D1", "decision": "fund a licensed feed, or keep the limited GitHub path",
             "suggestion": "S-L1"},
            {"id": "Q-V1", "decision": "what counts as an acceptable price source",
             "suggestion": "S-L4"},
        ],
        "next_round_if_approved": [
            "S-L1 path B: capture one named book with a timestamp, twice, and publish the check.",
            "S-L3 path A: build the two-season injury-to-line coefficient, and let it fail "
            "loudly if it fails.",
            "S-L4 path B: a named price tier with two-source agreement, so T14's market column "
            "becomes a market someone can bet into.",
            "S-L2 path A: rewards as rank and scrip, so requirement R-10 is satisfied without a "
            "legal exposure this repository cannot assess.",
        ],
        "counts": {
            "questions": q["counts"]["questions"],
            "suggestions": s["counts"]["suggestions"],
            "paths": s["counts"]["paths"],
            "defects_found": 7,  # L-01..L-03, B-01..B-04; F-01 is a finding, not a defect
            "values_published": corr["counts"]["values_published"],
        },
    }
    write_json("data/lab/summary.json", payload)
    print(f"summary written: {len(payload['what_is_new'])} deliverables, "
          f"{len(payload['defects_found_and_fixed_this_round'])} defects recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
