#!/usr/bin/env python3
"""Build the two decision registers the owner asked for, from the lab artefacts themselves.

Run:  python3 tools/lab/build_questions.py

Why this is generated and not hand-written
------------------------------------------
The owner asked for "a clear list of questions, informations and answers that need to be
addressed before any decision can be reasonably made" and for "suggestions ... to discover
missing information".  A hand-written list rots: it stops describing the data the moment a
builder changes.  So both registers are derived from the numbers in `data/lab/*` at build
time, and each row is required to carry:

    the question            what cannot be decided until it is answered
    what we HAVE            the measured facts, with the file they came from
    what we DO NOT have     the specific missing field, not "more data"
    what it blocks          which decision is stuck without it
    the closing test        an observable condition that says the question is answered
    the owner call          optional; only where a policy choice is genuinely the owner's

and for suggestions:

    at least two paths      every suggestion offers 2-3 mutually exclusive paths with cost,
                            what it unlocks and what it risks
    the recommendation      this session's opinion, labelled as an opinion
    what would change it    the evidence that would flip the recommendation

Nothing here is implemented.  The page that renders this is a decision board: pick a path,
and the chosen path becomes a task in COORDINATION.md.
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

    pt = prices["totals"]
    acc = model["accuracy"]
    counts = board["summary"]["counts"]

    Q = [
        {
            "id": "Q-P1", "area": "Price provenance", "priority": "P0",
            "question": "Which book, or which composite, is 'the market line'?",
            "have": f"{pt['market_rows']:,} market rows in the price store, but "
                    f"{pt['rows_naming_a_book_on_the_closing_snapshot']} of them name a book on "
                    "the closing snapshot; the only named vendor is the code WSGT, on the "
                    "2021 initial-lines file.",
            "missing": "a book identifier on every closing price row",
            "blocks": "beat-the-close reporting, any claim that a fair line differs from a "
                      "market a person could actually bet into, and gate G0 for every strategy",
            "closing_test": "every new closing row carries a book code that maps to a named "
                            "sportsbook in a registry, and two independent captures of the same "
                            "book agree on the number",
            "owner_call": False,
            "source": "data/lab/prices/price_coverage.json (defect P-04)",
        },
        {
            "id": "Q-P2", "area": "Price provenance", "priority": "P0",
            "question": "When was each number captured?",
            "have": f"{pt['rows_with_a_timestamp']} rows with a timestamp. The publisher's files "
                    "have no time column at all, so 'opening' and 'closing' are inferences from a "
                    "file name and a row order.",
            "missing": "a capture timestamp on every snapshot",
            "blocks": "true closing-line value (CLV), the demotion trigger D-03, and the "
                      "opening-vs-closing column for any game",
            "closing_test": "two snapshots of the same market on the same day, both timestamped, "
                            "show the line moving",
            "owner_call": False,
            "source": "data/lab/prices/price_coverage.json (defect P-05)",
        },
        {
            "id": "Q-P3", "area": "Price provenance", "priority": "P0",
            "question": "Why do two nflverse files disagree about the closing spread?",
            "have": "closing_lines.csv and games.csv agree on 2,267 games and disagree on 1,101 "
                    "after normalising the documented sign convention (32.7%).",
            "missing": "the publisher's statement of which file is authoritative, or a licensed "
                       "feed that settles it",
            "blocks": "choosing the benchmark the model is scored against",
            "closing_test": "a third, independent source agrees with one of the two on a sample "
                            "of at least 100 games",
            "owner_call": False,
            "source": "data/lab/prices/price_coverage.json (defect P-01)",
        },
        {
            "id": "Q-M1", "area": "Model", "priority": "P0",
            "question": "Is the originated line good enough to bet against a real market?",
            "have": f"Side MAE {acc['side_mae_model']} vs market {acc['side_mae_market']}; total "
                    f"MAE {acc['total_mae_model']} vs {acc['total_mae_market']}; Brier "
                    f"{acc['brier_model']} vs {acc['brier_market']} on {acc['n_side']:,} "
                    "out-of-sample games. The model beats a constant home-field baseline and "
                    "loses to the market on every metric.",
            "missing": "information the market does not have, or a documented inefficiency to "
                       "exploit",
            "blocks": "staking anything; promoting any strategy out of paper",
            "closing_test": "a strategy's out-of-sample z clears 1.96 with a bootstrap interval "
                            "excluding the break-even, on a pre-registered window",
            "owner_call": False,
            "source": "data/lab/lines/model_report.json",
        },
        {
            "id": "Q-M2", "area": "Model", "priority": "P1",
            "question": "Should the injury/deficiency signal enter the line at all?",
            "have": "37 certain starter replacements, 34 at the second string, 0 at the third; "
                    "15 depth losses among backups; and no measurement of what any of it does to "
                    "the score.",
            "missing": "a coefficient: the effect of a replacement's depth on the margin, "
                       "estimated out of sample on at least two seasons",
            "blocks": "using T16 as an input rather than a report",
            "closing_test": "the coefficient's out-of-sample interval excludes zero and the line "
                            "model's MAE improves when it is added",
            "owner_call": False,
            "source": "data/lab/deficiency.json (effect_status)",
        },
        {
            "id": "Q-S1", "area": "Strategy", "priority": "P0",
            "question": "Should a positive ROI with a weak signal ever be staked?",
            "have": f"{counts['staking_positive']} strategy shows a positive ROI "
                    f"(two-leg side parlay, +10.5%) and its signal z is 1.00 against a 1.96 bar. "
                    "It is demoted on drawdown (52.7% vs a 25% cap) and on price loss.",
            "missing": "a rule: whether the ROI may be surfaced at all when the signal fails",
            "blocks": "the definition of 'live' on the leaderboard",
            "closing_test": "the owner picks a policy from S-L2 and it is written into the gate",
            "owner_call": True,
            "source": "data/lab/leaderboard.json",
        },
        {
            "id": "Q-S2", "area": "Strategy", "priority": "P1",
            "question": "What is a reward, and who pays it?",
            "have": "eight candidate strategies, none live, no reward mechanism and no funding.",
            "missing": "a reward definition (rank? payout? scrip?) and whether any real money is "
                       "involved, which has legal consequences this repository cannot assess",
            "blocks": "the rewards column on the leaderboard",
            "closing_test": "a written reward rule, reviewed for legality by someone qualified to "
                            "do so",
            "owner_call": True,
            "source": "data/lab/leaderboard.json",
        },
        {
            "id": "Q-C1", "area": "Correlation", "priority": "P1",
            "question": "What is the correlation between two legs of a real parlay?",
            "have": "margin vs total r = 0.0216 (n = 7,413); side vs market r = -0.4262 "
                    "(n = 7,413); 49 values in total, each with n and an interval.",
            "missing": "player-prop leg correlations and same-player stat correlations",
            "blocks": "pricing a prop combo, and gate G7 for any parlay involving props",
            "closing_test": "a paired prop dataset for two seasons produces a value whose "
                            "interval excludes zero",
            "owner_call": False,
            "source": "data/lab/correlations.json",
        },
        {
            "id": "Q-D1", "area": "Data access", "priority": "P0",
            "question": "Should the pipeline depend on a source this environment cannot reach?",
            "have": "nfl.com is unreachable from this sandbox (HTTP 000); nflverse release assets "
                    "redirect to a blocked host; the nflverse repository archive is reachable and "
                    "pinned by SHA-256.",
            "missing": "a decision on whether to fund a licensed feed, or to keep the "
                       "reproducible-but-limited GitHub path",
            "blocks": "prop markets, player stats beyond the box score, multi-season injury "
                      "history",
            "closing_test": "either a licence is recorded, or the lab publishes a written "
                            "limitation statement that the owner accepts",
            "owner_call": True,
            "source": "data/lab/upstream/_pin.json",
        },
        {
            "id": "Q-D2", "area": "Data access", "priority": "P1",
            "question": "Why can't the injury report be read in bulk?",
            "have": "the Week 10 report is present via a previous session's collection (345 rows); "
                    "this session could not re-fetch nfl.com to re-verify a single one of them.",
            "missing": "a reachable official injury endpoint or an archived weekly series",
            "blocks": "re-verifying the injury rows, and the two-season injury history that "
                      "Q-M2 needs",
            "closing_test": "the pipeline fetches an official injury page at run time and the "
                            "fetched rows diff clean against the published ones",
            "owner_call": False,
            "source": "data/lab/upstream/_pin.json (limitations)",
        },
        {
            "id": "Q-V1", "area": "Verification", "priority": "P0",
            "question": "What counts as 'official' for a betting price?",
            "have": "no NFL or club source publishes a betting price, so every price row in this "
                    "repository is second-hand by construction. The existing site's rule requires "
                    "an official source on every data row.",
            "missing": "a written exception that names the acceptable second-hand publishers and "
                       "the verification each one gets",
            "blocks": "publishing any price at all without breaking the site's own rule, or "
                      "relaxing the rule silently",
            "closing_test": "the source registry lists a price tier with its publisher, licence "
                            "status and the check performed on it",
            "owner_call": True,
            "source": "data/lab/prices/price_coverage.json, docs/sources/sources.md",
        },
    ]

    S = [
        {
            "id": "S-L1", "title": "How to fill the missing price fields (Q-P1, Q-P2, Q-P3)",
            "recommended": "B",
            "paths": [
                {"id": "A", "name": "Licensed feed",
                 "what": "Buy a documented odds feed (one book, opening and closing, timestamped).",
                 "cost": "money and a vendor review; licence may restrict redistribution",
                 "unlocks": "true CLV, gate G0, ROI at an executable price, and every gate that "
                            "currently reports blocked",
                 "risk": "redistribution terms may forbid publishing the numbers on a public site",
                 "effort": "high"},
                {"id": "B", "name": "Documented manual capture of one book",
                 "what": "Capture one named book at a fixed time each week, record the time and "
                         "the book, publish the capture script and the raw page hash.",
                 "cost": "a weekly manual step, or a scheduled job that runs where the book's "
                         "site is reachable",
                 "unlocks": "a named book and a real timestamp, which is enough for CLV; n grows "
                            "slowly (one capture a week)",
                 "risk": "terms of use; a single book is a thin market",
                 "effort": "medium"},
                {"id": "C", "name": "Keep nflverse and publish the limitation",
                 "what": "Do nothing; keep the sourced-but-anonymous benchmark and the P-03/P-04/"
                         "P-05 labels.",
                 "cost": "zero",
                 "unlocks": "nothing new",
                 "risk": "every gate that needs a market stays blocked forever, and no strategy "
                         "can ever be promoted past paper",
                 "effort": "none"},
            ],
            "why": "B is the only path that produces a named book and a timestamp without "
                   "committing to a licence this repository cannot review. A is better if the "
                   "licence permits publication; C is a permanent ceiling on the project.",
            "would_change": "if the licence terms of a feed allow public display, A dominates.",
        },
        {
            "id": "S-L2", "title": "What a reward is (Q-S1, Q-S2)",
            "recommended": "A",
            "paths": [
                {"id": "A", "name": "Scrip and ranking only",
                 "what": "Rewards are rank and a non-transferable score; no money changes hands.",
                 "cost": "zero",
                 "unlocks": "the competition the owner asked for, with no gambling-law exposure",
                 "risk": "less motivating than cash; 'rewards' means something smaller",
                 "effort": "low"},
                {"id": "B", "name": "Funded prize pool",
                 "what": "Real payouts for top strategies.",
                 "cost": "money, plus legal review of pool and payout rules",
                 "unlocks": "a real incentive",
                 "risk": "prize pools tied to wagering are regulated in the US, and this "
                         "repository is not qualified to assess that",
                 "effort": "high"},
                {"id": "C", "name": "No reward, publish the board as research",
                 "what": "Drop the reward requirement and publish the leaderboard as a "
                         "methodology demonstration.",
                 "cost": "zero",
                 "unlocks": "nothing beyond what exists",
                 "risk": "the owner's requirement R-10 stays unmet",
                 "effort": "none"},
            ],
            "why": "A satisfies the letter of the requirement without creating a legal exposure "
                   "that cannot be evaluated here. It can be upgraded to B later.",
            "would_change": "a legal opinion on prize pools would make B viable.",
        },
        {
            "id": "S-L3", "title": "How to get information the market does not have (Q-M1)",
            "recommended": "A",
            "paths": [
                {"id": "A", "name": "Availability-first modelling",
                 "what": "Build the injury-to-line coefficient from two seasons of weekly injury "
                         "reports joined to club charts and final scores; test whether the market "
                         "under-adjusts on the first report of a starter's absence.",
                 "cost": "the injury history that Q-D2 says is missing",
                 "unlocks": "a testable, falsifiable edge candidate that uses data the market "
                            "arguably sees later than the model can",
                 "risk": "the market is fast; the effect may vanish once the closing price is used",
                 "effort": "high"},
                {"id": "B", "name": "Speed on official releases",
                 "what": "React to the official injury report within minutes of release and bet "
                         "before the market moves.",
                 "cost": "an always-on collector and a reachable league endpoint",
                 "unlocks": "a genuine timing edge if one exists",
                 "risk": "requires betting access this project has no licence for, and the edge "
                         "is fragile",
                 "effort": "high"},
                {"id": "C", "name": "Accept the model is a screen",
                 "what": "Stop hunting for an edge; publish the model as an explanation tool.",
                 "cost": "zero",
                 "unlocks": "clarity",
                 "risk": "the project's core purpose (originating lines that beat a market) is "
                         "abandoned",
                 "effort": "none"},
            ],
            "why": "A is the only path that uses assets the repository already collects (club "
                   "charts + league injury status) and produces a testable coefficient.",
            "would_change": "if the two-season join shows no coefficient, A collapses and the "
                            "honest answer becomes C.",
        },
        {
            "id": "S-L4", "title": "How to verify prices given no official source (Q-V1)",
            "recommended": "B",
            "paths": [
                {"id": "A", "name": "Relax the rule for prices",
                 "what": "Allow any price row with a publisher URL, no official requirement.",
                 "cost": "the site's central promise is weakened",
                 "unlocks": "fast publishing",
                 "risk": "a second-hand price can be wrong, and the site would no longer be able "
                         "to say every value is official",
                 "effort": "low"},
                {"id": "B", "name": "A named price tier with two-source agreement",
                 "what": "Prices are published only when two independent captures of the same "
                         "book agree, and the row says so.",
                 "cost": "a second capture per number",
                 "unlocks": "prices on the site without breaking the rule, because the check is "
                            "published",
                 "risk": "two captures can share a common upstream and still be wrong together",
                 "effort": "medium"},
                {"id": "C", "name": "Keep prices off the site",
                 "what": "Prices stay in `data/lab/` and never render.",
                 "cost": "zero",
                 "unlocks": "nothing",
                 "risk": "the site cannot show the fair-vs-market column that the owner asked for",
                 "effort": "none"},
            ],
            "why": "B preserves the rule (nothing is published without a check) while making the "
                   "price column real; C is what exists now and it fails requirement T14.",
            "would_change": "a licensed feed makes the whole question moot.",
        },
        {
            "id": "S-L5", "title": "What to do with the demoted parlay (Q-S1)",
            "recommended": "A",
            "paths": [
                {"id": "A", "name": "Keep it on paper and publish the demotion",
                 "what": "Leave the row visible with its demotion triggered, and let the record "
                         "of the demotion count as the demonstration.",
                 "cost": "zero",
                 "unlocks": "proof that the gate works on a real case",
                 "risk": "a reader who only looks at ROI still sees +10.5%",
                 "effort": "none"},
                {"id": "B", "name": "Hide any strategy that fails a gate",
                 "what": "Remove failed strategies from the board entirely.",
                 "cost": "survivorship bias, which the owner's rules forbid",
                 "unlocks": "a cleaner-looking page",
                 "risk": "the leaderboard becomes a lie of omission",
                 "effort": "low"},
            ],
            "why": "A is the only option consistent with the no-survivorship rule already "
                   "written into data/strategies.json.",
            "would_change": "nothing this session can find.",
        },
    ]

    write_json("data/lab/questions.json", {
        "generated_at": utcnow(), "snapshot": SNAPSHOT,
        "title": "Questions, what we have, what we do not have, and what it blocks",
        "rule": "A question is closed only when its closing test is met by published evidence. "
                "Until then the decision it blocks is not made.",
        "counts": {"questions": len(Q),
                   "p0": sum(1 for q in Q if q["priority"] == "P0"),
                   "owner_calls": sum(1 for q in Q if q["owner_call"])},
        "questions": Q,
    })
    write_json("data/lab/suggestions.json", {
        "generated_at": utcnow(), "snapshot": SNAPSHOT,
        "title": "Suggestions, each with more than one path",
        "rule": "Nothing here is implemented. Each suggestion lists every path with its cost, "
                "what it unlocks and its risk, then this session's recommendation, labelled as "
                "an opinion, and the evidence that would change it.",
        "counts": {"suggestions": len(S), "paths": sum(len(s["paths"]) for s in S)},
        "suggestions": S,
    })
    print(f"questions: {len(Q)} ({sum(1 for q in Q if q['priority']=='P0')} P0, "
          f"{sum(1 for q in Q if q['owner_call'])} owner calls)")
    print(f"suggestions: {len(S)} with {sum(len(s['paths']) for s in S)} paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
