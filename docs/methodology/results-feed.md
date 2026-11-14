# Verified results feed (T16)

**Session `arena-1d3600f8-x1` · 2026-11-14**

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
2. **Per-week game counts** against the expected slate: 16, 16, 16, 16, 15, 14, 14, 14, 15, 1 — all match.
3. **Per-team points for / points against** recomputed from the feed vs the official standings
   table (`data/standings_2026.csv`, itself verified against nfl.com/standings earlier on
   2026-11-14): **32 of 32 teams match, 0 mismatches.**
4. **Per-team W-L-T** recomputed from the feed vs the same standings: **32 of 32 match, 0
   mismatches** (including the Week 5 NYG–WAS tie).
5. **League totals**: Σ points in the feed = Σ PF in the standings = **6,291** exactly.
6. **Reference-only diff** against the third-party mirror (`data/processed/schedule_2026.json`):
   137 compared, **0 disagreements**. The mirror never changes a published value.

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

## Coverage note

Weeks 1–9 + the Week 10 Thursday game are settled and in the feed. Remaining Week 10 games
(Sun/Mon 2026-11-15/16) were unplayed at fetch time and are excluded — only settled games are
recorded. Weeks 11–18 will join the feed the same way as they settle.

## Sources used (all fetched 2026-11-14, none recalled)

* <https://www.nfl.com/schedules/2026/by-week/week-1> … <https://www.nfl.com/schedules/2026/by-week/week-10> (official)
* <https://www.nfl.com/standings/> via `data/standings_2026.csv` (official, previously verified)
* [nflverse/nfldata](https://github.com/nflverse/nfldata) (third-party mirror — reference diff only)
