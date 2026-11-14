# Validation Gates — How Strategies Earn Trust

Every strategy, model, and signal must pass these gates **in order** before it can be promoted to "validated" (eligible for leaderboard rewards). Gates are deliberately strict: the cost of a false edge is compounded bankroll loss.

## Gate A — Data integrity
- All inputs traceable: raw file + script + commit hash recorded.
- No look-ahead: every feature uses only information available at decision time.
- Values unverifiable from official sources remain blank + flagged, never inferred.
- **Fail example caught in this project:** the backup-QB signal showed a 7.7-point cover-rate *edge* (42.3%) when "backup" was defined using end-of-season QB frequency. Redefining it with kickoff-time information (prior-game starts only) erased the edge: 49.8% cover over n=2,156. The naive result was 100% look-ahead bias.

## Gate B — Sample size
- Game-level strategies: n ≥ 100 logged picks before ROI is reported; n ≥ 200 before "validated".
- Prop strategies: n ≥ 200 (higher variance).
- Variance math: a true 53.5% win rate at -110 has per-bet σ ≈ 1 unit; over n bets the win-rate standard error is √(p(1−p)/n) — at n=100 that is ±5.0pp (95% CI roughly ±9.7pp). Small samples cannot distinguish skill from luck; that is why the floor is 100, not 10.

## Gate C — Out-of-sample
- Walk-forward only: parameters fit on data up to time t, evaluated only on t+1 …
- Backtest window ≥ 8 seasons, then a live out-of-sample paper period (≥ 8 weeks) before real risk.
- No parameter re-tuning between the paper period and scoring.

## Gate D — Closing-line value (CLV)
- Primary metric. A pick "beats the close" if its taken price is better than the consensus closing line.
- Promotion threshold: mean CLV ≥ +0.5 points (spreads/totals) or ≥ +1.5% implied-probability (moneylines/props) across ≥ 50 closed picks.
- Why CLV: the closing line aggregates the most information; consistently beating it is the standard, outcome-independent evidence of edge (documented method, see leaderboard scoring weights).

## Gate E — Statistical significance with multiple-testing control
- Provisional: one-sided z ≥ 1.65 on CLV/ROI. Validated: z ≥ 2.0.
- When screening many signals (as this project does), apply Benjamini–Hochberg FDR 10% across the candidate family before celebrating any single z-score. Signal S3 (rest spot, z≈2.3 from one of 17 screened bins) stays **provisional** under this rule.

## Gate F — Stability
- Edge must persist across sub-periods (no single season > 50% of total profit; positive median quarterly CLV).
- Kill switch: rolling 30-pick CLV < −5% or Brier drift > 0.02 auto-suspends the strategy (suggestion SG-08).

## Gate G — Correlation caps
- Portfolio-level: correlated picks count once toward reward scoring.
- Parlay legs: measured correlation must be ≤ 0.35 (cap proposal); same-game parlays blocked until player-level correlations are measurable (OQ-4).
- Cross-game independence evidence: weekly home-cover variance ratio 0.99 (n=473 weeks) — multiplication pricing is fair across games.

## Gate H — Calibration
- Predicted probabilities vs observed outcomes: Brier score reported for every strategy; validated strategies need Brier ≤ book-implied baseline over the validation window.

## Gate statuses this week

| Strategy / model | A | B | C | D | E | F | G | H | Overall |
|---|---|---|---|---|---|---|---|---|---|
| Elo v0 model lines | ✅ | ✗ (no logged picks) | ✗ | ✗ | ✗ | ✗ | n/a | ✗ | **not validated — informational only** |
| S1 road favorites | ✅ | ✅ (historical) | ✗ | ✗ | ✗ | ✗ | n/a | ✗ | descriptive |
| S2 wind unders | ✅ | ✅ (historical) | ✗ | ✗ | ✗ | ✗ | n/a | ✗ | descriptive |
| S3 rest spot | ✅ | ✅ (n=287) | ✗ | ✗ | provisional z | ✗ | n/a | ✗ | provisional |
| S4 backup QB | ✅ | ✅ | ✅ | — | ✗ (no edge) | — | — | — | **failed — no edge** |
| S7 division low totals | ✅ | ✅ | ✅ | — | ✗ (no edge) | — | — | — | **failed — no edge** |
