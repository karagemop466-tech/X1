# Signal vs staking — leaderboard separation (T18)

**Session `arena-1d3600f8-x1` · 2026-11-14**

## What the owner asked for

> Separate 'signal' from 'staking' in the leaderboard so a lucky staking run cannot mask a bad signal.

## The rule

**final grade = min(signal, staking).** Staking can never rescue a failing signal.

* `eligible_for_ranking` requires **signal_gate = PASS first**. Staking metrics are used only to
  scale rewards among strategies that already pass the signal gate, and to cap risk (G5).
* Every signal metric is computed at **flat 1-unit stakes** on every bet — nothing stake-sized
  enters the signal grade.

## The two blocks

| Block | Metrics | Source |
|---|---|---|
| **signal_\*** | bets, W/L/P, hit rate + Wilson 95% CI, z vs break-even (52.38% at −110), flat ROI raw **and** top-5%-trimmed, ROI first/second window halves, luck share of profit, mean CLV (blank — Q-02), signal gate + reasons | flat 1u stakes |
| **staking_\*** | flat-stake units and max drawdown, ROI and max drawdown under a pre-registered variance-amplifying rule (2u after a win, 1u after a loss — demonstration only), largest single-bet share of gross wins, staking gate + reasons | stake-sized |

The momentum rule exists to *demonstrate the masking vector*: it moves ROI
(e.g. `S_cold_under` flat +2.27% → momentum +2.38%) without touching any signal metric. Under the
old single-column leaderboard that difference could reorder the table; under this rule it cannot,
because the strategy's signal gate is unchanged.

## Gate criteria referenced

* **G1** sample size (n ≥ 500 per family)
* **G2** skill above variance (z ≥ 1.96; hit-rate interval must exclude break-even)
* **G4** edge sign stable across window halves
* **G5** risk of ruin: drawdown ≤ 25% of a 100-unit bankroll under any registered staking rule

## Result at publication (mirror-window ledger, 16 strategies, 2015–2026)

* signal gate: **0 of 16 pass** — no strategy demonstrates skill above variance. The best z is
  `S_cold_under` at 0.01 (flat ROI +2.27% — pure variance, correctly not rankable).
* staking gate: 2 of 16 pass (drawdown cap under the momentum demonstration).
* eligible to rank: **0**. The board is honestly empty of promotable strategies.

## Provenance (flagged, per the verification contract)

The graded ledger is the third-party [nflverse/nfldata](https://github.com/nflverse/nfldata)
mirror window (`data/processed/strategy_bets.csv`) — labelled `mirror-window`, **NOT official**,
on every row. The official-only leaderboard (`data/leaderboard.json`) remains **unranked** until
gradeable results exist from official feeds; with the verified results feed (T16) now in place,
official grading starts as soon as prices enter the price-snapshot store (T15, Q-02).

## Files

`tools/build_signal_staking.py` → `data/leaderboard_signal_staking.csv` (one row per strategy,
columns prefixed `signal_` / `staking_`), `data/leaderboard_signal_staking.json` (rules +
provenance + rows).
