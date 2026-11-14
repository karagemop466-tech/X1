# Methodology — strategy leaderboard, validation gates, rewards (T6)

A leaderboard competition where **skill-based strategies win rewards and luck cannot**.

## Competition structure

- Anyone (or any model version) registers a **strategy**: a written thesis, its edge source,
  and the markets it bets (single bets, parlays, player-prop combos).
- Bets are appended to `data/strategies/bets.csv` with a timestamp **before kickoff** and the
  market line captured at bet time. Bets logged after kickoff are rejected at grading time.
- `code/leaderboard.py` grades bets, computes scores, checks gates, emits
  `data/strategies/leaderboard.csv` (the board) and `leaderboard_meta.json` (rules snapshot).

## Scoring (skill-weighted)

| Component | Rule | Anti-luck purpose |
|---|---|---|
| Single bet | +10 win, −11 loss, 0 push (vig-aware) | rewards profitability, not raw win rate |
| CLV bonus | +2 pts per full point of closing-line value | rewards *beating the closing line* — the most luck-resistant skill signal |
| Parlay | fair joint probability from marginal leg probs adjusted by the **measured** same-game φ (−0.023, n=1,496); payout scored vs that fair price | prevents naive multiplication from looking like skill |
| Correlated combos | legs sharing a game must declare φ; undeclared same-game legs rejected | blocks hidden correlation |
| Variance control | equity tracked per strategy; max drawdown recorded | one hot streak can't win a season |

## Validation gates (all required for `official` status)

| Gate | Requirement |
|---|---|
| G1 | Written thesis + identified edge source |
| G2 | Backtest ≥ 3 seasons, ROI > 0 after −110 pricing |
| G3 | ≥ 100 graded bets (≥ 25 for provisional display) |
| G4 | Binomial significance: P(win rate ≤ 52.4% breakeven) < 0.05 |
| G5 | Out-of-sample ROI > 0 |
| G6 | Portfolio correlation vs every official strategy ≤ 0.70 |
| G7 | Max drawdown ≤ 25 units in backtest |

## Removing luck — the arithmetic (computed in `data/strategies/luck_reference.csv`)

Bets at −110 break even at 52.4%. To *prove* an edge at 95% confidence you need:

| True win rate | Bets needed | Expected units over that sample |
|---|---|---|
| 54.5% | 1,522 | +61.5 |
| 55.0% | 991 | +49.5 |
| 56.0% | 515 | +35.6 |
| 58.0% | 211 | +22.6 |

Consequence: a hot 10-bet weekend proves nothing, and the leaderboard is built so that it
**cannot** win anything. Strategy status is mechanical: fewer than 25 graded bets → `unproven`;
25–99 → `provisional`; ≥ 100 + significance + positive equity + gates → `official`.

## Rewards

- Season pool (owner-funded; funding decision pending — open question Q7) paid
  **60 / 25 / 15** to the top-3 `official` strategies by season points.
- Reward eligibility requires `official` status at season end; provisional boards are display-only.
- All scoring is deterministic and re-runnable (`python3 code/leaderboard.py`) — no manual edits.

## Registered strategies (seeded 2026-11-14)

| ID | Name | Market | Status | Why |
|---|---|---|---|---|
| S1 | backup-qb-deficiency-fade | spread/total | blocked-data | needs historical depth charts (Q3/Q4) |
| S2 | injury-report-leverage | total | blocked-data | needs historical injury archive (Q4) |
| S3 | rest-travel-intl | spread | provisional | data available; isolation backtest pending |
| S4 | model-spread-edge | spread | **failed-gate** | v1 backtest ROI negative at all thresholds — measured honestly |
| S5 | model-total-edge | total | **failed-gate** | v1 totals ROI negative — measured honestly |
| S6 | correlated-parlay-book | parlay | provisional | needs live odds feed to compare prices (Q6) |

Nobody has earned points yet. That is the correct starting state for a system that refuses
to pay for luck.
