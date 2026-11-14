# Strategy leaderboard — a competition that rewards skill, not a hot streak

**Design goal.** Rank strategies so that the top of the board contains things that will keep
working, and so that the second-best thing (variance) is visible rather than hidden.

---

## 1. What a ticket is

| Shape | Registered as | Special gate |
|---|---|---|
| Single bet | one ticket, one leg | — |
| Cross-game parlay | one ticket, *k* legs | Gate 7 (dependence check) |
| Same-game parlay / prop combo | one ticket, *k* legs, shared game | Gate 7 **plus** joint calibration |
| Teaser / alternate line | one ticket | only if the settlement rule is recorded in full |

A ticket with an unrecorded settlement rule (for example, which book's void policy applies) is
**invalid**, because it cannot be graded.

## 2. Leaderboard divisions

Splitting by shape is not fairness theatre; the statistics genuinely differ.

| Division | Entry bar | Why separate |
|---|---|---|
| Singles | ≥ 500 scored bets | Lowest variance per ticket |
| Parlays (2–3 legs) | ≥ 300 tickets | Variance rises, margin compounds |
| Prop combos (same game, ≥ 2 legs) | ≥ 400 tickets | Dependence makes naive n misleading |
| Props (single player market) | ≥ 500 tickets | Distribution modelling differs from game markets |

A strategy may not appear in a division it has not qualified for. Cross-division "overall ROI"
comparisons are shown for information only and never for promotion.

## 3. Ranking objective

Do **not** rank by ROI. ROI is a magnitude; the thing we care about is whether the edge is real
relative to how noisy this market is.

```
Score = z_skill − λ · CalibrationPenalty − μ · DrawdownPenalty
```

where

```
z_skill = (p̂ − p_break) / sqrt(p̂(1−p̂)/n_eff)
```

| Term | Meaning | Starting weight |
|---|---|---|
| `z_skill` | Skill measured in units of its own uncertainty | 1.0 |
| `CalibrationPenalty` | Brier/log-loss deficit vs. the market-implied forecast | λ = 1.0 |
| `DrawdownPenalty` | Excess median drawdown above the 25% cap | μ = 0.5 |

Report the components, never just the composite. A high score built on a calibration penalty of
zero and a z of 0.4 is a *near-miss*, and it must look like one on the page.

## 4. Tie-breaks, in order

1. Higher `n_eff` (more evidence beats less evidence)
2. Lower calibration penalty
3. Smaller maximum drawdown
4. Earlier registration timestamp (rewards the strategy that existed before the result)
5. Alphabetical — never seniority, never the biggest stake

## 5. Rewards — design, not amounts

The requirement asks for rewards for top strategies. The **structure** can be specified now; the
**money** cannot, because funding, jurisdiction and tax treatment are unresolved owner decisions
(tracked as Q-07 in the Decision Register).

| Reward | Season 0 (paper) | Season 1 onward |
|---|---|---|
| Champion, per division | Title + badge only | Requires funded pool |
| Runner-up | Badge | Requires funded pool |
| Most-improved | Badge | Requires funded pool |
| **Best calibration** | Badge (awarded even without profit) | Recommended: keep non-cash |

**Design rules that prevent a rigged-looking board**

- **Reward calibration independently of profit.** Otherwise the board rewards the luckiest ticket
  selection. A well-calibrated strategy that loses money to margin is doing the hard part right.
- **No reward for a single hot window.** Champion requires two consecutive qualifying windows.
- **Clawback.** A title earned in a window later shown to contain a data error or a rule violation
  is vacated, and the vacating is logged publicly.
- **Entry is not pay-to-enter.** Charging entry while also running the book side invites a
  regulatory classification question that nobody in this repo is qualified to answer.
- **Fixed max entrants per window**, declared before the window opens.

## 6. The Season 0 reality

There is currently **no reward pool, no funded stake, and no logged forecast**. Season 0 is a
**paper league**: strategies run against frozen inputs, are graded, and appear on the board with
their gate results. That is not a degraded version of the idea — it is the only version of the
idea that produces evidence. Rewards attach after Gate 1–6 infrastructure exists.

## 7. Anti-gaming rules

| Attack | Rule |
|---|---|
| Cherry-picked start date | Window is fixed by the calendar, never by the entrant |
| Re-registering a failed strategy under a new name | Strategy hash includes inputs + features; duplicates are detected and rejected |
| Playing only soft numbers | Line-shopping gate (Gate 6) uses only release-time quotes |
| Undefined settlement | Ticket invalid without a recorded rule |
| Backfilled forecasts | Forecast must be timestamped before kickoff; late writes are voided from the window |
| Survivorship in reported results | Every registered strategy is listed, including the ones with zero bets |

## 8. What the public page shows

- Division and rank, with `z_skill`, `n_eff`, calibration penalty and drawdown **all visible**.
- Gate results per strategy: pass / fail / unscored, per gate. No aggregated "score" without components.
- Explicit "no strategies scored yet" state rather than an empty table pretending to be a ranking.

An honest empty leaderboard is worth more than a populated fake one.

## 9. Signal and staking are separate columns (T14)

**Requirement:** "Separate 'signal' from 'staking' in the leaderboard so a lucky staking run
cannot mask a bad signal."

The board publishes two scores with different jobs, and the ranking key only ever sees the
first one:

| Column | What it measures | Enters `rank_signal`? |
|---|---|---|
| `signal_score` | z of the observed win rate against break-even: `(p̂ − p_break) / sqrt(p̂(1−p̂)/n)` over decided bets. Stake-independent by construction — no equity, no drawdown, no compounding can reach it. | **yes — it is the rank** |
| `rank_signal` | 1..N by `signal_score` desc; ties break on larger `n`, then strategy id. Blank when `n = 0`. | — |
| `staking_score` | Realized units per decided bet (the P&L path's rate). | **no** |
| `equity_units`, `max_drawdown_units` | The flat-stake P&L path and its worst peak-to-trough. | **no** |

Rules that make the separation real rather than cosmetic:

1. **Unmeasured is blank, not zero.** A strategy with no decided bets has blank
   `signal_score`, `staking_score` and `rank_signal`. Publishing `0.0` would imply a
   measured signal of exactly nothing, which is a different — and false — claim.
2. **The rank key is computed in code from `signal_score` only** (`code/leaderboard.py`,
   sort block). There is no code path that lets `equity_units` or `staking_score` affect
   position. A strategy on a hot staking run with a win rate at break-even ranks *below*
   every strategy with a significantly positive win rate, whatever its units say.
3. **The mirror-image protection is stated too:** a good signal with an unlucky P&L path
   keeps its signal rank; the staking columns show the path without demoting it. Staking
   risk still *gates* (G5 drawdown cap) — gating is not ranking, and the gate's job is to
   bound ruin, not to measure skill.
4. **Status still requires both:** `official` needs the significance test (signal) **and**
   positive equity (economic reality). That conjunction can only ever *withhold* a title,
   never grant one — so it cannot mask a bad signal either way.

With Season 0 at zero logged bets every strategy is honestly blank/unproven today; the
columns exist so the first logged window is already scored under the separation rule.
