# Executive summary — round 2 (session `arena/907c5baf-x1`, 2026-11-14)

This round closed four standing gaps in the owner's brief with verified, reproducible
artifacts. Everything below is checkable from the links given; nothing is inferred.

## What shipped

1. **Verified results feed** (N1) — 150 games of the 2026 season transcribed from
   official NFL.com schedule pages. The feed's arithmetic reproduces the official
   standings for **all 32 clubs exactly** (W-L-T, PF, PA), and a community mirror agrees
   on 137/137 finals. Week 10 originated markets are settled from the official final;
   ROI is computable and published with n. [results feed](results-feed.md) ·
   `data/results_feed.json` · `app/results.html`
2. **Price-snapshot store** (N2) — opening and closing snapshots for every market we
   originate (56 rows: 14 games × spread/total/two moneylines), in origination order
   **side → total → moneyline**, with model fair line / market line / difference as
   separate columns. Market numbers are blank and flagged — no official source publishes
   prices — and the missed close on the played game is recorded as missed, not invented.
   [price store](price-snapshot-store.md) · `data/price_snapshots.json` · `app/prices.html`
3. **Signal/staking leaderboard split** (N3) — rank is computed from signal metrics only
   (hit rate, flat-stake ROI, CI, p, luck-removed ROI); staking diagnostics (drawdown,
   losing streak) live in a separate, explicitly unranked scorecard, so a lucky staking
   run cannot mask a bad signal. `data/leaderboard_split.json` · `app/leaderboard.html`
4. **Demotion gate** (N4) — defined and pre-registered: five triggers (two failed
   windows, negative-edge evidence, CLV decay, drawdown, data-integrity breach) send a
   live strategy back to paper; signal-only inputs; re-promotion requires a fresh
   pre-registered window. Numeric thresholds are labelled proposed defaults pending
   owner ratification (Q-26). [demotion gate](methodology/demotion-gate.md) ·
   `data/demotion_gate.json` · `app/validation.html`

## What the numbers say (and do not say)

- The one graded game (WAS 24 @ NYG 21) settled 3W-3L across the six legs of our three
  markets; moneyline ROI at our prices is **−3.3% on n = 1** — computable, not
  meaningful. No skill claim rests on it.
- The research-lab backtests (16 strategies, community-mirror data) remain **labelled
  unverified**; exactly one (wind-under) passes all eight gates on that benchmark, and
  the benchmark itself is an open decision (Q-02).
- Correlations published by the live pipeline are computed from official numbers only
  and carry **n with every value** (988 pairs, n = 32 team-level).

## Open decisions (nothing is implemented ahead of these)

| ID | Decision | Blocks |
|---|---|---|
| Q-26 | Ratify or amend the demotion thresholds (T2–T4) | demotion gate going live |
| Q-31 | Which price source is authoritative for market open/close snapshots | market columns of the price store, CLV trigger T3 |
| Q-32 | The staking plan (fractional Kelly? flat?) and unit size | staking scorecard becoming more than a flat-unit diagnostic |
| Q-33 | Settlement authority and grading window for the results feed | automated grading job |
| Q-34 | Reward funding and payout legality (carried from Q-06/Q-25) | leaderboard rewards going live |

## Verification performed this round

- 137 official scores transcribed and cross-verified (32/32 standings identities, 137/137
  mirror agreement).
- `tools/verify_stores.py` enforces the store invariants in CI: origination order,
  open/close columns present, market cells blank-or-sourced, n beside every correlation
  value, ranking rule string present, demotion gate defined.
- Full existing check suite re-run before merge (see the coordination record).
