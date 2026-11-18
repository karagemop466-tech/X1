# Round 6 — audit reply, executive summary and the decisions still open

Dated 2026-11-18, session `arena/efb06932-x1`, branch `arena/efb06932-x1`.
Every number below was read from a file in the tree at commit time; the command that reproduces each
one is named beside it. Nothing here is estimated, and where a value could not be verified the row
says so.

## Executive summary

Six things changed since round 5, and one of them is a correction to something we had already
published.

1. **The Game Center venue collector works, and it was wrong before it was right.** 27 fixture pages
   (Weeks 10–11) are now captured on a schedule, retained as hashed gzip (6.35 MB), and published as a
   35-column register. The first published register mislabelled **all 13 unplayed Week 11 fixtures as
   `FINAL`** — a page-wide status search had hit the word `FINAL` in a standings table lower on the
   page — and printed `AT&amp;T STADIUM` because HTML entities survive tag-stripping. Both defects
   were found by cross-checking against an *independent hand transcription of the same official pages*
   (`data/nfl/venues_2026_week10.csv`, PR #86/#87), which went from 12/14 agreeing to **14/14**. The
   register now publishes the parse method per cell (`venue_method`, `status_method`, `score_method`),
   a parser version stamp, and `verify`/`cross-check`/`selftest`/`reparse` commands that run in CI.
   Scores stay blank on all 27 rows because the page renders them as `Hidden Score` in the text layer;
   capacity, roof, surface, attendance, weather and officiating stay blank on all 27 because the
   fixture page prints only `Location` and `Stadium`. Those are limits of the source, recorded as
   flags, not gaps to fill.
   → `docs/methodology/venue-and-fixture-context.md`, `console/venue-capture.html`

2. **Fixture context is now derived from the capture instead of being blank.** 13 Week 11 fixtures,
   **13 with a stadium**, rest days for 12 away and 10 home teams, previous venue, same-city travel,
   `international` (`yes` only for MIN@SF at Estadio Banorte, Mexico City), and `prime_time` taken from
   the slate's own window label rather than a kickoff threshold we invented. 0 roof and 0 surface
   cells, by rule.
   → `python3 tools/official/fixture_context.py build && ... check` (PASS, 13 rows reproduce)

3. **Injury is now a delta, not a level — and the measurement refutes the cadence.** A surprise ledger
   over the 5 retained reads of the league hub: **0 status movements**, reads spanning 2 calendar days,
   two of them three minutes apart. Cadence verdict: *not met* against the brief's
   Wednesday/Thursday/Friday requirement. The tool is the deliverable; the empty result is the honest
   answer, and it turns into a scheduling decision (SG-17) rather than a modelling feature.
   → `python3 tools/official/injury_delta.py build / check / status`

4. **Every frozen probability now carries its inputs, and re-derives from them.** The Week 11 escrow
   (52 rows) is published with its full input vector — per-club games, point differential, shrunk
   ratings and points for/against, the corpus league average, and the four pre-registered constants read
   *by import* from PR-01 so this table cannot drift from the registration. **26 of 26** in-scope
   published probabilities re-derive to within half a unit of the last published digit; the 26 total
   rows are outside the check by design because they publish a line, not a margin probability.
   `check` fails the build on any row that will not re-derive.
   → `python3 tools/official/escrow_provenance.py inputs / check`

5. **The "removal of luck" panel exists, and says how small the sample is.** Proper scores (Brier)
   against a coin *and* against the 0.55 home baseline, with a **game-cluster** bootstrap (10,000
   draws, seed 20261118) because the escrow stores three or four markets per fixture and treating them
   as independent would roughly halve the interval. Today: 1 settled row of 66 in the ledger, 0 from
   Week 11 — the panel demonstrates the arithmetic and states the sample the gate needs, and it is
   explicitly **not** a leaderboard entry, because the pre-registration rule keeps backtest and
   settlement numbers out of the leaderboard.
   → `python3 tools/official/escrow_provenance.py score`, `console/luck-panel.html`

6. **Both sides of "what would change our mind" now exist for every strategy, in numbers.** 16 of 16
   strategies (100%) carry a confirm cell and a refute cell; the checker fails if either cell contains
   no digit, and the first draft failed it — 6 of 16 rules were prose and had to be rewritten against a
   numeric standard. Each row carries the shared holdout window (prospective escrow only) and the
   multiplicity note (Bonferroni 0.05/16 = 0.003125); a met refutation retires the rule rather than
   reopening it for re-parameterisation. → `python3 tools/official/mind_change.py build / check`,
   `console/mind-change.html`

**One published row was found false and has been corrected with the measurement that replaced it.**
Q-02 on the decision register asserted that opening prices "do not exist for any season except 2021".
They now exist for 2026: the store holds **104 2026 opening rows across 26 Week-10 fixtures** (snapshot
`OPEN-2026`, source `nfldata_games`). The row was rewritten to read from the store instead of from
memory, and states what is still missing: **0** of those rows carry a close, the price is the mirror's
uniform `-110`, and the capture stamp dates our read, not the book's post. The conclusion survives —
a residual against the market and closing-line value remain uncomputable — but the stated reason no
longer does.

Site state after this round: **35 pages**, `verify_console` PASS with **0 unsourced table rows**, every
link resolving. New pages: `venue-capture.html`, `injury-delta.html`, `escrow-inputs.html`,
`luck-panel.html`, `mind-change.html`.

## What I need from you (the only blocking items)

These are decisions, not questions I can answer by reading a source. Each has a path chosen as a
recommendation; none is built ahead of your pick.

| # | Decision | Recommendation | If you say nothing |
|---|---|---|---|
| 1 | **SG-16** — how wide to point the venue capture | Backfill the season once, keep only the current fortnight's bytes, retain raw pages for any fixture that enters a feature set | Stays at 27 of 285 fixtures |
| 2 | **SG-17** — injury capture cadence | Daily reads of the team hub; revisit hourly only if the daily series moves and we miss it | Injury stays a register, not a model input |
| 3 | **SG-18** — fund the escrow sample vs widen the backtest | Freeze forecasts weekly, forever; never lower a gate to get a promotion | Zero strategies promote, correctly |
| 4 | **SG-01** — pay for a price feed, or self-capture on a cron | Path B after a terms-of-service review; path A if there is budget | Price-dependent requirements (CLV, demotion on price, residual schedule) stay unmet |
| 5 | **Game Books** | Not available to us: reuse requires written NFL permission | Venue/officiating detail stays out of the pipeline |

## Questions / information / answers register — the state of what we know

Read `console/questions.html` for the full 18 rows with sources; this is the shape of it. A row is
`ANSWERED` only when the answer came from a source we hold and re-read; `BLOCKED` names the missing
source; `OWNER DECISION` names the decision.

| id | area | status | what it turns on |
|---|---|---|---|
| Q-01 | Signal | ANSWERED — no | model RMSE 14.198 vs market 13.14 (n=6,102); we cannot yet beat the close |
| Q-02 | Prices | BLOCKED — corrected today | openings exist for 26 Week-10 fixtures, 0 paired closes; CLV still uncomputable |
| Q-16 | Fixture context | ANSWERED — and it corrected our own table | venue register 27 rows, 243 cells re-derived, 14/14 vs the hand read |
| Q-17 | Injury | ANSWERED — instrument works, cadence does not |8 reads, 0 deltas, cadence not met |
| Q-18 | Governance | ANSWERED | 16/16 strategies falsifiable in numbers; 26/26 escrow probabilities re-derive |

## Suggestions board (19 rows, `console/suggestions.html`)

Round 6 added SG-16 (capture width), SG-17 (injury cadence), SG-18 (escrow funding vs gate-lowering)
and SG-19 (publish the registers as tables — done in this round, listed here so the decision record
shows what was built and on whose path). Each row carries 2–3 paths with cost, effort, risk and what
each one unlocks; nothing was implemented ahead of a decision except SG-19, which was additive and
self-contained.

## Irregularities flagged for review (`console/flagged.html`, 14 rows)

New this round, both recorded rather than quietly fixed:

* **X-13** — the false-`FINAL` and entity defects in our own published register, what each one taught
  (bounded score-box region; entity decoding; a `parser_version` stamp so a re-parse is
  distinguishable from a re-read).
* **X-14** — the two official reads of "which fixtures exist" disagree for Week 10 (14 vs 13) because
  the week page was read before a rescheduled game appeared on it. Both files carry
  `fixture-set-mismatch` flags; neither was aligned by hand. A fixture set is only as good as the
  moment it was read.

Carried from earlier rounds and still open: stale `week_schedule` reads, 825 undated price rows, 46
depth-review rows with no source, the 260-row price-store re-download, Munich stand-alone week
labelling.

## Handoff to the integration session

1. **`tools/official/readiness.py` rows R-15, R-16, R-17, R-18 can now be measured, not described.**
   I did not edit that file (shared, additive-rows-only rule). The values to plug into the `today`
   column, each from a file CI writes:
   * **R-15** (fixture context) → `data/official/fixture_context/fixture_context_meta.json`
     `counts`: 13/13 stadium, 12 away + 10 home rest days, 0 roof, 0 surface.
   * **R-16** (probability + inputs) → `data/official/escrow/escrow_inputs_meta.json`:
     `rows_rederived_ok` 26 / `rows_in_rederive_scope` 26, `rows_out_of_rederive_scope` 26 by design.
   * **R-17** (removal of luck) → `data/official/escrow/luck_removal_meta.json`: 1 group,
     `settled_rows` 1 / `ledger_rows` 66, `week11_settled` 0, bootstrap 10,000 draws.
   * **R-18** (two-sided mind change) → `data/console/mind_change_meta.json`:
     `strategies_with_both_sides` 16 / `strategies` 16, coverage 100.0.
   Until that edit lands, those four rows understate what the tree contains — which is safe, but it is
   the one place the site is now wrong in our favour's direction.
2. **The 258 remaining fixtures.** Everything needed is in the collector; the blocker is retention
   policy (SG-16), not code. Do not widen `WEEKS` without deciding what happens to `raw/`.
3. **`cross-check` is advisory by design** — a non-zero mismatch count must not fail the capture job;
   it must reach the Flagged page. Keep it that way: the alternative is a pipeline that hides
   disagreement to stay green.
4. **Do not re-transcribe Week 10 venues by hand.** The runner and `tools/verify_venues_w10.py` are now
   two independent reads of the same official pages; their agreement is the verification. Replacing
   one with the other destroys the only check either has.

## Reproduce everything in this file

```
python3 tools/official/gamecentre.py selftest && python3 tools/official/gamecentre.py verify \
  && python3 tools/official/gamecentre.py cross-check
python3 tools/official/fixture_context.py check
python3 tools/official/injury_delta.py check && python3 tools/official/injury_delta.py status
python3 tools/official/escrow_provenance.py check
python3 tools/official/mind_change.py check
python3 tools/build_console.py && python3 tools/verify_console.py
```
