# Correlation — the math, and the exact data you need before a number is publishable

The requirement was "determine correlation values". This document specifies the estimator, the
test, and the failure modes, so that when a correlation **is** published it is defensible. No
correlation value is published today, because the joint-outcome dataset does not exist yet. A
number invented here would be indistinguishable from a guess.

---

## 1. Definitions

For two binary legs *A* and *B* with indicator outcomes `1{A}` and `1{B}`:

```
p_A = E[1{A}]          p_B = E[1{B}]          p_AB = E[1{A}·1{B}]
Cov(A,B) = p_AB − p_A·p_B
σ_A = sqrt(p_A(1−p_A))        σ_B = sqrt(p_B(1−p_B))
ρ = Cov(A,B) / (σ_A·σ_B)                     # defined only when σ_A, σ_B > 0
```

Two degenerate cases must be handled explicitly, not silently:
σ_A = 0 (a leg that always wins or always loses) makes **ρ undefined**, not zero.
Report it as "undefined (zero variance)" and drop it from the parlay's pricing model.

## 2. Why the sign is not enough

Correlation tells you the *direction* of dependence. The parlay's fair price depends on the
**joint probability** `p_AB`:

```
fair decimal odds(A and B) = 1 / p_AB
```

ρ and `p_AB` are not interchangeable. Two legs can have ρ = 0.35 and still require completely
different pricing at different base rates. Always publish `p_AB` (with an interval) next to ρ,
or publish nothing.

## 3. The independence trap, with the arithmetic shown

Two legs at p = 0.5 each, both priced at −110 (decimal 1.9091). A book that takes both legs pays about
`1.9091² = 3.645` (≈ +264). What that is worth depends entirely on the joint probability:

| Assumption | Joint probability `p_AB` | Fair decimal | Fair US | Book pays | Book margin |
|---|---|---|---|---|---|
| Independent (ρ = 0) | 0.2500 | 4.000 | +300 | ≈ +264 | **+8.9%** (book keeps the edge) |
| ρ = 0.30 | 0.3250 | 3.077 | +208 | ≈ +264 | **−18.5%** (edge flips to the bettor) |

`p_AB` is fixed exactly for binary legs once ρ is chosen: `p_AB = p_A·p_B + ρ·√(p_A(1−p_A)·p_B(1−p_B))`,
which at p = 0.5 reduces to `p_AB = 0.25 + 0.25ρ`.

The second row is why books cap, reject or re-price correlated legs. It is also why a parlay strategy that
ignores dependence will backtest beautifully and lose in production: the backtest priced the ticket at
`1/(0.5·0.5) = 4.0` when the true joint was `1/0.325 = 3.08`. The error is in our favour in the backtest and
against us at the window.

> Margin note, so nobody quotes the wrong multiple: at −110 a single leg carries a 4.55% hold, and the hold on
> an *independent* k-leg parlay is `1 − 1.9091^k / 2^k`. That is 8.88% at two legs (≈1.95× one leg), 13.03% at
> three (≈2.87×) and **20.75% at five legs (≈4.6× one leg)**. Margin compounds roughly linearly in the number of
> legs, not at a constant multiple of 2.5.

## 4. Estimation procedure (mandatory before any published value)

1. **Define the setting.** Same game, same player, same drive conditions. A correlation measured
   across different conditions is an average of things that do not pool.
2. **Estimate on training data only.** Chronological split. Never random split — that leaks future
   information into the past.
3. **Bootstrap the interval.** Report a 95% interval on both ρ and `p_AB`. With ~17 games per team
   per season, intervals are wide; a point estimate without an interval is not a finding.
4. **Test the independence null.** Likelihood-ratio or a permutation test. Publish the p-value and
   the number of observations, because n is what makes the value believable or not.
5. **Confirm out of sample.** The correlation must survive on held-out seasons. A correlation that
   exists only in the fitting window is noise with a bibliography.
6. **Correct for multiple comparisons.** If we test 200 leg pairs, roughly 10 will clear p < 0.05 by
   chance. Use a Benjamini–Hochberg style correction and report the adjusted threshold.

## 5. Sample-size reality check

To detect ρ = 0.10 against a null of zero at 80% power, you need on the order of **several
thousand** paired observations (Fisher z approximation: `n ≈ ((z_{1−α/2}+z_{1−β})/z_ρ)² + 3`,
which is ≈ 780 for ρ = 0.10 at α = 0.05, power 0.80, and larger once you condition on game states).
At 272 games per season that is **multiple seasons** of joint data for a single well-conditioned pair.
Any published correlation from one season of one team's props should be treated as a hypothesis.

## 6. Which pairs to test first (priority order)

| Priority | Pair | Why it matters |
|---|---|---|
| 1 | QB passing yards × own WR/TE receiving yards | Mechanically coupled; largest and most stable dependence |
| 2 | Team total × own RB rushing yards | Game-script coupling |
| 3 | Opposing QB passing yards × our team's pass-rush props (sacks) | Negative dependence; frequently mispriced |
| 4 | WR1 receiving yards × WR2 receiving yards (same team) | Competes for targets; usually negative, sometimes positive |
| 5 | Game total × any single player's over | Game-state coupling |
| 6 | Spread cover × QB/rushing props | Game-script coupling |

Pairs 1–2 are where a well-estimated joint distribution is most likely to differ from the naive
product. That is the only reason to do this work.

## 7. Storage contract

Every published correlation row must carry:

`leg_a`, `leg_b`, `setting`, `n_observations`, `p_a`, `p_b`, `p_ab`, `rho`, `rho_ci_low`,
`rho_ci_high`, `p_value`, `test_correction`, `train_window`, `holdout_window`, `source_dataset`,
`source_url`, `retrieved_at`, `status`.

`status` is one of `published` (all fields filled and passed) or `unverified` (published on the
Flagged for Review page). The generator refuses to emit a `published` row with any blank field,
which is how the rule "never fill in a value" is enforced mechanically rather than by good intentions.

## 8. Official-only rule, and n on every value (T15)

**Requirement:** "Compute correlations only from officially sourced numbers and publish n with
each value."

**The rule, as implemented:**

1. **Inputs.** A correlation may be computed *only* from numbers read off a committed
   official snapshot — the NFL.com standings transcription and the NFL.com team-stats
   tables. Mirror data (nflverse) may benchmark, but a mirror-derived correlation is never
   part of the requirement's set and is labelled third-party wherever it appears.
2. **n.** Every published value carries its sample size. For the club-level set that is
   `n = 32` (the 32 clubs, one observation each) — on every row, no exceptions.
3. **Publication rule** (reproduced exactly, see below): a pair is published iff
   `( |r| ≥ 0.40 or either side ∈ {PF, PA, NET_PTS, W, PCT} )` **and** `|r| < 0.99`. The
   0.99 cut suppresses mechanically identical columns — a completed pass is both a `Cmp`
   and a `Rec`, so those pairs are `r = 1.000` by construction and publishing them would
   be noise, not information.
4. **Verification.** `python3 tools/verify_official_correlations.py` recomputes all
   **988** published rows from the official snapshots and fails the build on any
   mismatch. Result on 2026-11-14: **988/988 recomputed within 0.0015, 988/988 with
   n = 32, 988/988 official nfl.com sources only, 0 duplicates, publication set
   reproduced exactly.** The line-by-row ledger is `data/verify/official_correlations.csv`
   (pair, published r, recomputed r, delta, n, source, status).

**Irregularity found while verifying (recorded, not silently fixed):** the dataset's own
`method` text describes only the first half of the publication rule — it does not mention
the `|r| < 0.99` redundancy cut. The cut was reverse-engineered by exact set reproduction
(988 = 988, zero differences), so no published value is wrong; the documentation gap is
logged for review rather than edited into another session's file.

**What stays outside this set, and why:** same-game spread/total φ, cross-game residual
correlations, prop-family pairs and the strategy×strategy matrix are computed from
third-party market or mirror data — useful, labelled, but *not* the requirement's
official-only set. The strategy matrix additionally publishes cells without a per-cell n
(it is derived from a shared-games count the payload does not expose per pair); that gap is
flagged rather than guessed.
