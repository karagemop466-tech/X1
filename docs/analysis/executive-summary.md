# Executive summary

**Project X1 — NFL data, verification, and decision system** · snapshot date 2026-11-14 (UTC)
· session `arena-a78e0158-x1` · branch `arena/a78e0158-x1`

## What this is

A verified, source-linked NFL research base with three products:
1. **A live GitHub Pages site** — every table row carries an official source link; unverifiable
   values are blank and flagged, never inferred.
2. **An original line-origination engine** (`code/build_lines.py`) — the project's own spreads and
   totals, fitted on game results only, validated leak-free against market benchmarks.
3. **A strategy leaderboard** (`code/leaderboard.py`) with validation gates, measured correlation
   values, and a reward structure designed so luck cannot be paid.

## Season state (verified 2026-11-14)

- Week 10 in progress: 137 of 272 regular-season games played; season opened Wednesday Sept 9
  (NE@SEA, Seattle defending Super Bowl LX champion). Super Bowl LXI: Feb 14, 2027, SoFi Stadium.
- Week 10: 14 games (TNF result: WAS 24, NYG 21), byes CHI/DEN/PHI/TB, Munich game NE@DET,
  MNF LAC@BAL. Full slate on the Schedule page.
- Standings leaders through the Thursday game: BUF 7-1, SF 7-1, DEN 7-2, CHI 7-2; LAC 0-8,
  MIA/TEN 1-7. All 32 rows cross-verified NFL.com ↔ nflverse (exact match).
- Record nine international games in 2026 (Melbourne, Rio, 3× London, Paris, Madrid, Munich,
  Mexico City) — a structural signal source (travel/rest) unique to this season.

## Verification results

- Standings: 32/32 exact cross-source match. Week 10 schedule: 14/14. International: 9/9.
- Injury report: 345 official rows transcribed with per-player links.
- 12 irregularities flagged (roster surprises, QB conflicts, stale input datasets) — published on
  the **Flagged for Review** page; none block the release.

## Findings that matter for decisions

1. **The v1 model has no betting edge — and that is measured, not assumed.** Edge vs market ROI:
   −6.1% (spreads) to −5.5% (totals); improving to −2.6% at a 7-point disagreement threshold.
   Strategies S4/S5 are registered as `failed-gate`. The path forward is model v2 with
   QB-adjustment (the single biggest missing feature, visible in LAC@BAL and SEA@LV).
2. **Same-game spread/total correlation is ≈ 0 in this dataset** (φ = −0.023, n=1,496; margin-total
   r = 0.020) — same-game parlays price ≈ naively; cross-game independence is confirmed
   (r = 0.001, n=12,585). Correlation control is therefore cheap but must still be enforced.
3. **Luck cannot be paid by design.** At −110, proving a true 55% capper takes 991 bets at 95%
   confidence; the leaderboard gates encode exactly that arithmetic (CLV bonuses, 100-bet minimum,
   binomial significance, drawdown caps).
4. **Injury/depth tracking is blocked by one missing input**: official depth charts. The official
   injury report (345 verified rows) supports load flags today; deficiency scoring needs the
   discovery actions in open questions Q3/Q4.

## Decisions needed from the owner (full matrix: open-questions.md)

- Q6 odds feed for live market comparison & CLV (blocks reward-grade CLV scoring),
- Q7 reward-pool funding & size,
- Q3 depth-chart data collection (unlocks S1/S2 and the deficiency score),
- Q2 model v2 priorities (QB adjustment recommended first),
- Q10 risk posture (units per bet, stop-loss).

## Flagged for review (headline items)

Myles Garrett on LAR and Aaron Donald on LAR listings need confirmation (F1/F2); five star-player
team changes are single-sourced (F3); the BAL Week 10 QB conflict is unresolved until Monday
inactives (F4). Full list with links on the Flagged for Review page.
