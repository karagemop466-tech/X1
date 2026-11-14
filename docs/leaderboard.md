# Strategy Leaderboard — Competition & Rewards Design

A season-long competition between strategies. Strategies earn the right to compete by passing the [validation gates](validation-gates.html); they earn rewards by scoring well against **luck-adjusted** metrics.

## 1. Entry rules

1. A strategy = a written rule set + a bet ledger. Every pick is logged **before kickoff**: timestamp (UTC), strategy ID, market, side, taken line/odds, book, model probability, rationale link.
2. No retroactive entries. A pick not in the ledger before kickoff does not exist.
3. Minimum activity: ≥ 100 closed picks and ≥ 8 active weeks before ROI is displayed publicly (Gate B).
4. Correlated picks (Gate G) count once toward reward scoring.

## 2. Scoring (proposed weights — awaiting decision OQ-8)

| Component | Weight | Metric |
|---|---|---|
| CLV score | 40% | mean closing-line value vs consensus close (the luck-removal core) |
| ROI score | 30% | units won ÷ units risked, on closed picks |
| Calibration | 15% | Brier score vs book-implied baseline |
| Stability | 15% | consistency across sub-periods (Gate F) |

Composite Score = weighted sum, normalized 0–100. Luck adjustment is structural: CLV (40%) is outcome-independent, calibration punishes overconfident models, and minimum-sample gates keep variance-driven hot streaks from topping the board.

## 3. Tiers and rewards (proposed — awaiting decision OQ-1/OQ-2)

| Tier | Criteria (end of season or rolling 12 weeks) | Proposed reward |
|---|---|---|
| 🥇 Champion | Composite ≥ 80 and Gates B–H passed | 50% of reward pool |
| 🥈 Challenger | Composite 65–79 | 30% of reward pool |
| 🥉 Analyst | Composite 50–64, all gates passed | 20% of reward pool |
| — | Below 50 or any failed gate | no reward; strategy review |

The reward **pool** (real money vs points vs privileges) is decision OQ-1 — intentionally left open.

## 4. Anti-gaming rules

- Line-shopping-only entries (picking+EV from stale lines without a model) are scored on the worst book's close, not the best.
- Maximum 5 correlated-adjacent picks per slate.
- Strategies must publish their rule set; changes reset their history (new strategy ID).
- All ledger rows auditable in-repo (JSON, committed with timestamps).

## 5. Weekly cadence

Mon: data refresh + flags → Tue: model lines published → Wed: pick ledger committed pre-kickoff → Sun/Mon: games played → Tue: scores updated, digest published ([suggestion SG-01](suggestions.html)).
