# Methodology — originating our own NFL lines (T5)

Goal: price every game **from game results only**, benchmark against the market (which is a
benchmark, not truth), and keep a full audit trail. No market input is used to fit ratings.

## 1. Model

Two ordinary-least-squares systems over 32 team ratings + one home parameter, fitted on
per-game observations from nflverse `games.csv` (1999-classic format, REG games only):

- **Scoring system** (65 variables): `home_pts = O_home − D_away + HOFF`, `away_pts = O_away − D_home`
- Constraints (hard, weighted 1e4): `mean(D) = 0`, `mean(O) = league average points per team per game`
- Solved by normal equations + Gaussian elimination with partial pivoting (pure stdlib).
- Spread = predicted home margin; total = predicted combined points.
- Moneylines via normal approximation with the empirical residual SD (spread ≈ 13.9, total ≈ 13.8).

Final fit for Week 10 lines: **2019–2025 + all 2026 played games (137)** = 2,008 games.

Known v1 limitations (tracked, see open questions):
- No QB adjustment — the model cannot see that BAL is without Lamar Jackson, that SEA starts
  Drew Lock, that MIA starts a rookie, or that ARI changes quarterbacks (market lines DO see this).
- Uniform season weighting (no recency decay), no offensive/defense coaching or scheme features.
- Home field fitted globally (0.69 pts in the final fit — the modern league-wide figure).
- The mean(O)/mean(D) constraints split home scoring advantage slightly differently than a
  free-parameter model would; predictions (margins/totals) are unaffected.

## 2. Leak-free validation

Backtest with an expanding weekly window: every historical game priced using ratings fitted
**only on games completed before that week** (no in-week leakage, warmup of 80 games).
1,779 games scored across 2019–2025.

| Season | Games | MAE spread (pts) | MAE total (pts) |
|---|---|---|---|
| see data/lines/backtest_summary.csv | 1,779 total | 10.91 | 11.06 |

The market's own closing-line RMSE is ≈ 13.3 on the same data; our model RMSE ≈ 13.9 —
i.e., the v1 baseline is close to but below market quality, exactly what a results-only model
without QB/situational features should produce. This is the honest baseline the leaderboard
gates protect against.

## 3. Edge economics (betting our disagreements)

Rules: bet our side when the model differs from the market by ≥ threshold; flat −110 pricing.
Full bet log in `data/lines/backtest_bets.csv`; summary in `backtest_summary.csv` and
`threshold_sweep.csv`.

Result (v1): **negative ROI at every threshold** (spreads −6.1% → −2.6% at 7-pt threshold;
totals −5.5% → −13.6%). Interpretation: the market already prices what a results-only model
knows, plus things it can't (QB news). Strategy S4/S5 are therefore registered as
`failed-gate` — that is the system working, not a failure of the system.

## 4. Week 10, 2026 — originated lines (X1)

`data/lines/originated_lines_2026_week10.csv` — our own spread/total/ML for all 14 games
(next to the market benchmark), with the model-input statement on every row. Examples:
- SEA@LV: X1 −6.5 (market −6.5) — model and market agree exactly.
- BUF@NYJ: X1 −13.5 (market −8.5) — model is higher on Buffalo; market bakes in MetLife/Jets
  situational factors our v1 model cannot see.
- LAC@BAL: X1 +7.5 (market +4.5) — the model cannot see Lamar Jackson's IR stint (limitation F4/QB);
  treat as informational until model v2 adds QB adjustments.

**Usage rule:** X1 lines are the project's own prices for benchmarking and strategy development.
They are not betting recommendations. Any live strategy must pass the leaderboard gates first.

## 5. Correlation values (computed, not assumed)

From `data/lines/correlation_report.csv` (n and 95% CIs on every value):
- Game margin vs game total: **r = 0.020** (n=1,496, CI −0.031..0.071) → no exploitable linkage.
- Same-game favorite-cover vs over: **φ = −0.023** (n=1,496) → same-game spread+total parlays are
  ~independent in this dataset; P(over | favorite covers) = 0.473 vs P(over) = 0.485.
- Model spread error vs total error: **r = 0.025** (n=1,779).
- Cross-game, same-week residual correlation: **r = 0.001** (n=12,585 pairs) → different games
  are effectively independent; multi-game parlays price with naive multiplication (up to vig).

Player-prop correlations are **not computable** from in-repo data (no official prop results feed) —
flagged as missing information with a discovery path (open questions Q5/Q6).
