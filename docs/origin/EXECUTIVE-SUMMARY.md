# Executive summary — round N (session `arena/3fa49c1a-x1`, 2026-11-14)

## What this round was

The owner directed eight improvements to be implemented now (the bolded items of the
brief). All eight are built, verified, and published. Nothing else was changed.

| # | Directive | Shipped | Where |
|---|---|---|---|
| N1 | Price-snapshot store: opening and closing numbers for every market we originate | 56 rows, one per originated market selection, CLV-ready schema; openings blank (no source records 2026 openers), closings recorded from the fingerprinted third-party mirror, every price cell flagged UNVERIFIED pending a licensed feed (Q-02) | `data/prices/`, `tools/build_originated_markets.py`, `app/prices.html` |
| N2 | Verified results feed so backtests and ROI can be computed | **137 completed 2026 games** (weeks 1–10) read from nfl.com schedule pages; verified by standings arithmetic (32 clubs × W/L/T/PF/PA = 160 checks, **all pass**; league ΣPF = ΣPA = 6291) and a 137/137 cross-match against the third-party mirror | `data/results/`, `tools/build_results.py`, `app/results.html` |
| N3 | Originate the side first, then the total, then the moneyline | Order **enforced in the builder** (14 sides → 14 totals → 28 moneylines; the build fails if the order breaks) | `tools/build_originated_markets.py`, `app/origination.html` |
| N4 | Model fair line, market line, difference as separate columns | Three separate columns on every row, one sign convention (difference = fair − market; moneylines in win-probability points) | `data/lines/originated_markets_2026_week10.csv` |
| N5 | Separate signal from staking in the leaderboard | SIGNAL block (flat-stake: hit rate, mean CLV, CLV t-stat, edge at close — promotion/demotion read only this) vs STAKING block (ROI at rule, drawdown, growth — reporting only) | `data/leaderboard_split.json`, `app/leaderboard.html` |
| N6 | Track the depth of the replacement | 78 starter slots with a game status: 68 replaced by **2nd string**, 1 by **3rd string**, 9 with no replacement listed; offense, defense and special teams; each row re-verified against the club chart and the injury report | `data/depth/`, `tools/build_replacement_depth.py`, `app/replacement-depth.html` |
| N7 | Correlations from officially sourced numbers only, n published | **3,570 pairs** over 85 NFL.com metrics × 32 clubs, each value carrying n and p; independent recomputation agrees with the published table **905/905** | `data/correlations/`, `tools/build_correlations_official.py`, `app/correlation.html` |
| N8 | Define a demotion gate (live → paper) | D1 CLV decay, D2 drawdown (≥25 units or ≥35% of peak), D3 hit-rate decay, D4 data-integrity trip, D5 re-promotion (50 new graded bets, no reuse of pre-demotion data). Closes Q-26, unblocks G-13 | `data/gates_v2.json`, `app/validation.html` |

## Verification performed this round

1. **Results feed:** every score transcribed from the official weekly schedule page and then
   re-derived against the league standings — each club's W-L-T, points for and points against
   computed from the feed must equal the official standings exactly. 160/160 checks pass.
   League identity ΣPF = ΣPA = 6291 holds. The third-party mirror agrees on all 137 scores
   (used as cross-check only, never as source).
2. **Flag I-14 resolved by that arithmetic:** the standings *do* include the Thursday Week 10
   result (WAS 3-5-1 / NYG 5-3-1 are post-game records). The earlier "pre-game record" reading
   was wrong; the 32-club check passes with the game included and fails without it. No data
   discrepancy exists between the schedule and the standings.
3. **Replacement depth:** every published row re-verified before writing — the starter must be
   depth 1 on the club chart, the replacement the next listed name at its string depth, and the
   game status must match the official report exactly. 78/78 pass after fixing the known
   Green Bay jersey-number printing issue (flag F-01) in the matcher.
4. **Correlations:** recomputed independently from the official tables with textbook formulas;
   905 overlapping pairs agree with the published pipeline table to ±0.002 (905 agree, 0 disagree).
5. **Price store:** no value is presented as verified. Openings are blank because nothing records
   them; closings carry `verified=no` and the mirror's provenance; CLV columns are blank.

## What is deliberately still blank or open

- **Every price cell** (Q-02): no official or licensed source publishes betting prices. The store
  exists and is ready; the feed choice is an owner decision (suggestion S-01 paths A/B/C).
- **Leaderboard result columns:** blank until verified prices and graded bets exist. Ranks would
  be noise. The signal/staking split is structural and fills automatically once they do.
- **Promotion thresholds** (Q-07/Q-09): the tests are named; the minimum sample and correction
  method remain owner-settable before the first strategy goes live.
- **Houston depth chart** (F-03): still unparsable; its slots are absent, not guessed.

## Where to look

- Decisions taken (the eight directives, each linked to its artefact): `app/suggestions.html`,
  `data/origin/decisions_taken.json`
- Question/answer updates (Q-02, Q-03, Q-04, Q-22, Q-26): `app/decisions.html`,
  `data/origin/question_answers.json`
- New pages: `app/results.html`, `app/origination.html`, `app/prices.html`,
  `app/replacement-depth.html`
- Flagged-for-review items remain non-blocking and are published on `app/flagged.html`.
