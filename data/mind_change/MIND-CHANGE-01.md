# MIND-CHANGE-01 — the two-sided mind-change rule for every strategy entry

Registered 2026-11-18 (UTC), before any Week 11 game has kicked off. The commit that carries this
file is the registration, in the same sense PR-01 to PR-04 use it: `tools/build_mind_change.py`
publishes the SHA-256 of this file with every number, and `tools/verify_mind_change.py` fails the
build if the file no longer hashes to what the register records. A threshold edited after the
results are in is not a threshold.

## Why this exists

The owner brief asks for one thing on this page that neither published strategy table has:

> "Add a two-sided 'what would change our mind' field to every strategy entry."

The lab leaderboard carries a `falsifier` on each of its eight rows — the observation that would
make us **abandon** it. The console's strategy table carries no such field at all. One-sided is how
a losing strategy survives a review cycle: the bar to keep testing is never stated, so testing
continues indefinitely, and the bar to *adopt* is stated loosely, so a near-miss is never closed.
This rule fixes both sides and fixes them as arithmetic.

## The rule

For a strategy entry with `n` decided bets, an observed hit rate `p̂`, the break-even rate `p0` that
its own prices imply (0.523809… at −110; a compounded bar for a parlay; the published per-market bar
for a moneyline entry), and an interval on the edge `[lo, hi]`:

1. **Adopt** when the published interval lies entirely **above** break-even: `lo > 0`.
2. **Abandon** when the published interval lies entirely **below** break-even: `hi < 0`.
3. The interval used is the one the entry's own table publishes, so this register never disagrees
   with the page a reader can already see: `data/console/strategy_results.csv` publishes `CI_LOW`
   and `CI_HIGH` on the **edge** scale, and `data/lab/leaderboard.json` publishes
   `hit_rate_ci95` on the **rate** scale, which is converted to edge against the same bar.
   An entry whose table publishes no interval is evaluated on the recomputed interval of section 5.
4. **Neither** is the honest current state for many entries, and the register publishes, for each,
   the number of additional bets that *would* move it into one of the two states at the observed
   rate: `n* = ceil((1.96 / |p̂ − p0|)² · p̂(1−p̂))`, rounded up. Because the site's published
   intervals are not the normal approximation, `n*` is labelled with its own basis and is a lower
   bound where the published interval is wider.
5. Where `p̂` is on the wrong side of `p0`, **no sample can promote the entry at the observed rate**
   — the register prints that sentence instead of a big number. That is the sentence this rule
   exists to make unavoidable.
6. The rate needed to promote at today's sample is also published:
   `p* = p0 + 1.96·√(p0(1−p0)/n)`. If `p*` is far above `p̂`, the entry needs a better model, not a
   longer test.
7. A **recomputed** one-sided 95% normal interval on `p̂` is published beside the verdict
   (`lower_bound`, `upper_bound`, `half_width`). Where the recomputed interval and the published one
   give different verdicts, the row is flagged `interval methods disagree` and no mind-change
   verdict is claimed — the disagreement is the finding, not a rounding detail.
8. For a parlay or combo entry, the bar `p0` is the product of its legs' break-evens **only when**
   the joint probability has been validated directly; where it has not, the row says the bar is
   undefined and no mind-change number is published. Multiplying marginals is not a probability
   (this is the SG-06 gate, applied to this register).

## What this rule does not do

- It does not promote anything. Promotion additionally requires the eight gates
  (`docs/methodology/validation-gates.md`); this register supplies only the mind-change fields, and
  a row that reads "ADOPT-eligible on this test" is a statement about one test.
- It does not touch the frozen rules PR-01 to PR-04 or the pre-registration register. Those files
  are not edited here; this is a companion register.
- It does not use ROI. ROI needs a price, and there is no licensed price source (R-02 / Q-02), so
  both sides of the test are hit-rate tests against the break-even the price implies.
- It does not pretend to be a frequentist correction for multiplicity: 24 entries are tested at
  z = 1.96 each, and the multiplicity question is Q-10's, not this file's.
