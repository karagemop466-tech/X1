# Verified results feed (T16)

**Session `arena-1d3600f8-x1` · 2026-11-14 · Week 10 closure by `arena-473e08d5-x1` · 2026-11-17**

## Which file is the feed today

| File | Rows | What it is |
|---|---|---|
| `data/results/verified_results_2026_r3.csv`, `..._n2.csv`, `verified_results.json` | **150** | **The current feed.** Weeks 1-10 complete, every row transcribed from the official by-week page, reconciled against the standings page read on the row's own date. |
| `data/results/verified_results_2026.csv` | 137 | The **2026-11-14 dated view**: the same double-entry build, bounded by the verbatim anchor captures in `data/results/raw/week_NN.md` and by the standings snapshot taken that day. Correct for its date, not current — `coverage_scope` in `verification_report.json` says so on the record. |

Two artefacts, two dates, one rule: a feed is only ever as current as the official page read it was
transcribed from, and it never silently outruns its own evidence.

## What the owner asked for

> Add a verified results feed so backtests and ROI can be computed at all.

## What exists

| Artifact | Purpose |
|---|---|
| `data/results/raw/week_01.md` … `week_10.md` | Evidence snapshots: the verbatim result anchor texts fetched from the official `https://www.nfl.com/schedules/2026/by-week/week-N` pages on 2026-11-14, one file per week, with the fetch method recorded. |
| `data/results/verified_results_2026.csv` | **The feed.** 137 settled games (Weeks 1–9 complete, Week 10 through TNF). Every row: teams, final score, status `Final`, ISO date + verbatim date label, `game_url`, `source_url` = the official nfl.com game page, `verification=verified-official`. |
| `data/results/verification_report.json` | Machine-readable double-entry verification record. |
| `tools/build_results_feed.py` | Parses the evidence into the feed and runs the cross-checks. |
| `tools/verify_results_feed.py` | Offline CI checker: re-parses evidence, compares every cell to the committed feed, re-runs the standings checks, enforces the provenance contract. |
| `tools/grade_roi.py` | Grades bets against the feed and computes ROI: `data/results/graded_bets.csv` (689 bets, each carrying the official game URL) + `data/results/roi_summary.csv`. |

## Verification performed (double entry)

1. **Row-level transcription** from the official by-week schedule pages (22 anchor texts pages,
   both chunks each). Verbatim anchors preserved in `data/results/raw/`.
2. **Per-week game counts** against the expected slate: 16, 16, 16, 16, 15, 14, 14, 14, 15, 1 — all match
   at the 2026-11-14 view; the 2026-11-17 closure takes week 10 from 1 to **14** and the feed from 137
   to **150**, with `tools/verify_2026_11_17.py` V1 re-proving slate completeness (14 fixtures + 4 byes =
   32 clubs, each exactly once).
3. **Per-team points for / points against** recomputed from the feed vs the official standings
   table (`data/standings_2026.csv`, itself verified against nfl.com/standings earlier on
   2026-11-14): **32 of 32 teams match, 0 mismatches.**
4. **Per-team W-L-T** recomputed from the feed vs the same standings: **32 of 32 match, 0
   mismatches** (including the Week 5 NYG–WAS tie).
5. **League totals**: Σ points in the feed = Σ PF in the standings = **6,291** exactly at the 2026-11-14
   view, and **6,923 = 6,923** (Σ PF = Σ PA) over the 150-game closure.
6. **Reference-only diff** against the third-party mirror: 137 compared, **0 disagreements** at
   2026-11-14; **150 compared, 0 disagreements** at the closure. The mirror never changes a published
   value. Since 2026-11-17 the comparison reads the **pinned bytes** (`data/raw/nflverse/games.csv`,
   sha256 `5a61d312…`, 2 190 568 B, fetched 2026-11-17T23:05:12Z) rather than a derived file, because two
   fetches of the mirror 21 minutes apart that morning returned **different bytes** — the first without
   the Sunday Week 10 scores. V9 fails the build if the file on disk and `data/raw_manifest.json` stop
   agreeing, which is the only defence against a cross-check silently drifting under a citation.

Any single transcription slip would break at least one of checks 3–5; all are green.

## How ROI is now computed (`tools/grade_roi.py`)

* **Outcomes** — settled from the verified feed only. Each graded bet row carries the game's
  official nfl.com URL.
* **Prices** — conventional **−110 flat stake**, an explicit assumption (`assumed_-110`), because
  no official or licensed price source exists (Q-02). When the price-snapshot store gains real
  captures, the grader can switch to recorded prices.
* **Lines** — the model's fair lines are our own computation; the market benchmark is the
  nflverse mirror and is labelled third-party, not official.

Published 2026-11-14 (137 verified games, 689 graded bets): no strategy is positive at assumed
−110; best is `MODEL_SIDE_5` at −0.67% (n=27). Model accuracy vs verified results: spread MAE
**10.05 pts**, total MAE **11.31 pts**. These agree with the earlier mirror-window finding
(F-07) and are published as the honest state: **the model is a screen, not a price.**

## Coverage note (updated 2026-11-17)

Weeks 1–10 are settled and in the feed (150 games). The 13 Sunday/Monday Week 10 games were unplayed when
the feed was built on 2026-11-14, so they joined on 2026-11-17 from a fresh official read — appended, never
overwritten: the row already in the feed (Week 10 TNF) is byte-identical in both reads, and each row keeps
its own `read_at`. The Monday-night game `LAC 23 @ BAL 20` was still `Scheduled` on 2026-11-16, so it is
the one promotion in this closure and it is evidenced at its own Game Center page
(`data/verification/2026_11_17/official_gamecentre_LAC_BAL_2026_11_17.txt`).

Weeks 11–18 join the same way. Three rules made that true, and they are the reason the closure was one
change and not thirteen edits:

* **Dated baseline.** The feed is reconciled against a *frozen* standings transcription
  (`data/verification/2026_11_17/official_standings_2026_11_17.tsv`), not against the rolling collector
  file. A rolling baseline makes "verified" self-fulfilling — the feed would be checked against whatever
  the collector last fetched, and a coverage gap would vanish by redefinition instead of by evidence. The
  rolling parse is still used, but only as a *second reader of the same page* (check V6), where a
  disagreement means a parser defect.
* **Coupled baselines move together.** Transcription, row-count pin, standings baseline, mirror pin: moving
  the rows alone left 23 of 32 clubs disagreeing with the standings the feed is validated against.
  `tools/build_results_r3.py` now takes its expected count from `N_EXPECT = 150` and its standings from
  the dated pack; the signal-join pin is expressed as `len(feed_rows)` instead of a literal, so it cannot
  rot on the next closure.
* **Joins are measured, not assumed.** `game_id` spellings differ between sources
  (`2026_10_LA_ARI` in the mirror, `2026_10_LA_AZ` in the feed, `..._ARZ` in an earlier read), so the
  closure joins on matchup + date with an explicit `ARZ→ARI / AZ→ARI / LAR→LA` normalisation and fails on
  any fixture that matches on one side only.

## Sources used (all fetched 2026-11-14, none recalled)

* <https://www.nfl.com/schedules/2026/by-week/week-1> … <https://www.nfl.com/schedules/2026/by-week/week-10> (official)
* <https://www.nfl.com/standings/> via `data/standings_2026.csv` (official, previously verified)
* [nflverse/nfldata](https://github.com/nflverse/nfldata) (third-party mirror — reference diff only)

## Correction, 2026-11-17

The bullet above this section's 2026-11-14 heading read "Week 10: 1 of 14 verified" on the published
pages for three days while the official page printed 14 finals. That was not a wrong number, it was a
right number past its date — the artefact was correct as of 2026-11-14 and the site did not say which of
the two it was quoting. Every coverage figure on the results page now carries the read date of the page
it came from, and the 137-row artefact carries `coverage_scope` in its own report.
