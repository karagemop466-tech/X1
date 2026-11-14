# Validation gates — the conditions a strategy must pass before it is scored, ranked, or rewarded

A gate is a **pre-registered** threshold. It is written down *before* the test window opens, so
that it cannot be moved after the results are known. Moving a gate after seeing results is how
strategy shops manufacture skill from noise.

Gates are checked in order. Failing an early gate stops the strategy; there is no "but the ROI
looks good" exception.

---

## Gate 0 — Provenance (blocks everything)

| Check | Pass condition |
|---|---|
| Registered before the test window | `registered_at` precedes `test_start` |
| Inputs are licensed and timestamped | Every input row carries a source and a retrieval time |
| No look-ahead | No field in the feature set was published after the forecast cut-off |
| Settlement rules defined | Market, side, period, push rule and void rule are written down |
| Reproducible | Model version + hyperparameters hashed and stored |

If Gate 0 fails, the strategy is **unscored**. Unscored is not failed; it is unknown, and unknown
never enters the leaderboard.

## Gate 1 — Sample size

| Market | Minimum scored bets | Rationale |
|---|---|---|
| Singles | **500** | At a 55% true hit rate, 500 bets gives a standard error on hit rate of ≈ 2.2 pts |
| Two-leg parlays | **300 tickets** | Higher variance per ticket |
| 3+ leg parlays / prop combos | **400 tickets** | Variance grows again; plus dependence makes the effective n smaller |

**Effective n for correlated parlays.** If tickets share legs, they are not independent draws:

```
n_eff = n / (1 + (k − 1)·ρ̄)
```

where *k* is the average overlap. 400 tickets with ρ̄ = 0.3 and k = 2 is effectively **308**. Report
`n_eff`, not the raw count, and hold the gate against `n_eff`.

## Gate 2 — Skill above variance

The signature of luck is that a strategy's result is inside the range a coin flip would produce.

```
SE(p̂) = sqrt(p̂(1−p̂)/n)
z = (p̂ − p_break) / SE(p̂)          # p_break = the break-even hit rate after margin
```

A market at −110 requires `p_break = 110/210 = 0.5238`. A strategy hitting 55.1% over 500 bets:

```
z = (0.551 − 0.5238)/sqrt(0.551·0.449/500) = 0.0272/0.0222 ≈ 1.22
```

**z ≈ 1.22 is not skill.** It is a coin landing 55 heads in 100. This is the exact calculation that
removes luck from the equation, and it is why a 55% record over a season is not evidence.

Gate 2 passes at **z ≥ 1.96** (two-sided 5%) **and** a bootstrap 95% interval on ROI that excludes 0.
Both, not either.

## Gate 3 — Calibration

Being right on average while being wrong per-bet is not a model.

| Metric | Pass condition |
|---|---|
| Brier score | Better than the market-implied Brier score on the same events |
| Log loss | Better than market-implied log loss |
| Reliability slope | Fitted slope on a calibration plot in **[0.85, 1.15]** |

A strategy that wins money but is badly calibrated is a strategy that got lucky on which bets it
chose. It will not repeat.

## Gate 4 — Robustness (the luck filter that matters most)

| Test | Pass condition |
|---|---|
| **Regime split** | Sign of edge is the same in both halves of the test window |
| **Leave-one-team-out** | Refit without each club; edge survives in ≥ 28 of 32 refits |
| **Season split** | Edge survives in a second season (or a second independent window) |
| **Placebo** | Randomised label/date shuffles do not reproduce the edge |
| **Sub-period stability** | No single 3-week block contributes > 50% of total profit |

The leave-one-team-out test is the direct antidote to "we found an edge, it was the Ravens".
If removing one club destroys the strategy, the strategy *was* that club's luck.

## Gate 5 — Risk of ruin and drawdown

| Test | Pass condition |
|---|---|
| Max drawdown | Median simulated drawdown ≤ 25% of bankroll |
| Staking rule pre-registered | Fixed-fraction or flat, declared before the window |
| Staking invariance | Strategy survives a 50% reduction in stake size (edge is not leverage) |
| Unlimited-loss exposure | **Automatic fail** if any leg has unbounded downside without a stated cap |

Gate 5 is where "the line looked right" meets "did the account survive".

## Gate 6 — Economic reality

| Test | Pass condition |
|---|---|
| Line shopping | Edge survives using only the best available quoted price at release time |
| Stated limits | Stake at the registered size is executable at the recorded limit |
| Margin and fees | All fees, and the vig, are inside the ROI calculation |
| Rounded stake prohibition | No position requires an implausible stake for the amount of profit claimed |

Professional-looking ROI on stakes nobody would be allowed to place is the most common way a
backtest lies. Gate 6 exists solely to kill those.

## Gate 7 — Correlation discipline (parlays and combos only)

| Test | Pass condition |
|---|---|
| Dependence measured, not assumed | Published ρ with interval, per `correlation.md` |
| Joint calibration | Predicted joint probability is calibrated on holdout |
| n_eff reported | Effective sample size reported alongside raw tickets |
| Combinatorial cap | No ticket with > 6 legs passes Gate 7 without a separate joint model |

---

## Scoring rules that prevent luck from entering the leaderboard

1. **Score only within the registered window.** Anything outside it is practice, and practice is not scored.
2. **Passes count.** Every pass is logged; a strategy that only logs winners has no denominator and is invalid.
3. **Arithmetic market return.** No compounding. Compounding turns a lucky streak into an unreadable number.
4. **Trim, then report both.** Report raw ROI *and* ROI with the best 5% of tickets removed. If the two
   diverge by more than the margin, the strategy is a few tickets wearing a costume.
5. **Promotion is slow.** A strategy reaches Champion only after **two consecutive** qualifying windows.
   One window promotes to Contender, never to Champion.
6. **Demotion is automatic and uncapped.** Two failed windows demote. No sitting on a past result.
7. **Shadow period.** A Challenger runs alongside the leaderboard for one full window before it can
   displace anything, so that a lucky month cannot knock out a verified strategy.
8. **Everyone sees the same data.** Leaderboard entrants are evaluated on identical frozen inputs;
   otherwise the competition measures data access, not skill.

## Where each gate is implemented

`data/gates.json` holds the machine-readable version of this page, and
`tools/verify_data.py` asserts that every strategy on the leaderboard carries a
gate-by-gate result. A strategy with a blank gate cannot be marked `published`.
