# PR-01 — singles-only shadow baseline (team strength, no market)

**Registered:** 2026-11-16, by session `arena-543cdcb0-x1`. The commit that first adds this file is the
registration; `tools/build_preregistration.py` resolves that commit from git and stores the SHA-256 of
this file next to it, so an edit after the fact is detectable rather than deniable.

**Status of what this rule produces:** a **backtest** for weeks 3–10 and a **prospective shadow record**
from week 11 forward. Per the standing rule — *"forbid backtest numbers from ever appearing on the
leaderboard"* — nothing computed under this registration may be ranked against a strategy that is
competing for a reward. Backtest numbers belong on the methodology page, with their window named.

## The rule, in full, before any model output was looked at

**Model.** A team's strength is its own **average point differential per game played**, shrunk toward the
league mean (0.0) by a fixed prior weight:

```
raw(t)   = ( sum of (points_for - points_against) over the games t has played ) / games_played(t)
rating(t) = raw(t) * n(t) / (n(t) + K)          K = 2.0 games  (frozen, see below)
```

**Prediction.** For a game with home team `h` and away team `a`:

```
expected_margin(h) = rating(h) - rating(a) + H        H = 1.6 points (frozen)
p(home wins)       = Phi( expected_margin / SIGMA )   SIGMA = 13.5 points (frozen)
```

`Phi` is the standard normal CDF. A tie is counted as a half-win for the home team in the probability
score, matching the -110 convention the site already publishes; ties are counted, never discarded.

**Originated markets, in the required order.** For every game the model produces three numbers and they
are published as three columns, never merged:

| order | market | fair line | market line | residual |
|---|---|---|---|---|
| 1 | side | `-expected_margin` for the home team, in points | blank | blank |
| 2 | total | `expected_total = league_avg_team_points*2 + (rating(h)+rating(a)) * TOTAL_SHIFT` with `TOTAL_SHIFT = 0.0` in this version, i.e. the league-average total, published as the honest floor of this model (a margin model has no total information) | blank | blank |
| 3 | moneyline | American price implied by `p` at a stated zero-vig conversion | blank | blank |

`market line` is blank because no official price source exists in this repository (open question `Q-02`),
and `residual = fair − market` is therefore blank too. **A blank is not zero.** The residual column is
the single number the whole origination programme is judged on, so it stays visibly empty until a price
policy is decided; publishing a residual built from a third-party mirror would rank a strategy on data
the owner has not agreed to use.

**Evaluation protocol.**
1. **Chronological only.** A game is predicted from ratings built exclusively from games whose date is
   strictly earlier. No refitting on the evaluation window, no backfilling, no "current" rating.
2. **Score with proper scores.** Brier score and log loss for the win probability. Accuracy is reported
   beside them, never instead of them.
3. **Skill is benchmark-relative.** Brier skill score against two frozen benchmarks: (i) the constant
   0.5 forecast, (ii) the no-information home baseline 0.55 for the home team. These are the same two
   controls every other strategy is measured against (PR-02).
4. **Uncertainty is a game-cluster bootstrap.** Resample *games* (the unit of independence, not bets),
   10,000 draws, seed recorded in the artefact, report the mean and the 2.5th percentile. The lower
   bound, not the point estimate, is what a claim of skill has to clear.
5. **Multiplicity is counted, not assumed away.** `n_trials` = the number of registered model variants
   scored on the same window; the interval is widened by a Bonferroni factor and `n_trials` is published
   with the result. This version has `n_trials = 1` because exactly one variant was written above, and
   `K`, `H` and `SIGMA` have not been touched since.
6. **The luck panel is mandatory output.** Realised wins minus expected wins (`sum p`) for a bettor who
   always takes the model's side, and the standard deviation of that difference
   (`sqrt(sum p(1-p))`). If the gap is inside one standard deviation, the record is not evidence of
   anything and the page says so in those words.
7. **Calibration, not just discrimination.** Reliability in five probability bins, published with the count
   in each bin; a bin with fewer than 10 games is printed but marked too-small.

**Why the frozen constants are frozen at those values, not fitted.**
`K = 2` (a two-game prior — a fourth of a season, deliberately weak), `H = 1.6` (the long-run NFL home
margin, a published fact rather than a fit to these 149 games), `SIGMA = 13.5` (the approximate standard
deviation of an NFL margin). If any of them is re-tuned to improve the score, this registration is
void: the entry's hash will not match the file, `build_preregistration.py` will say
"edited after registration", and the number becomes a new pre-registration with a new window. That is the
whole mechanism.

**Promotion / demotion.** The shadow baseline never enters the leaderboard. It can be *promoted* to a
registered competing strategy only by a new entry with a new rule file (and therefore a new commit), a
window that starts in the future, and the demotion gate wired in — a strategy that drops below
benchmark-relative skill 0 on the trailing 4 game weeks goes back to paper automatically.

**Two-sided "what would change our mind" for this entry.**
* *Would confirm it:* a positive lower-bound Brier skill vs the 0.55 home baseline over a prospective
  window of at least 100 games, at `n_trials` disclosed.
* *Would refute it:* a skill lower bound below 0 for two consecutive prospective game weeks, or a
  calibration slope outside 0.6–1.4 on the same window, or the realised-minus-expected gap exceeding
  2 standard deviations in either direction (which would mean the record is luck, not signal, whatever
  the score says).
