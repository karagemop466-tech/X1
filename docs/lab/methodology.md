# Methodology — originated lines, signal vs staking, and the demotion gate

Session `arena/56769365-x1`. This file states the method once, in the same words the site
uses, so that a reviewer can check the page against the method rather than against intent.

## 1. Origination order: side, then total, then moneyline

The order is a mathematical constraint, not a preference. A moneyline is P(home wins), and
that probability is a function of the same scoring distribution that produces the spread and
the total. Derive it first and you are inventing a probability and reverse-engineering a
spread from it; derive it last and it is a consequence of two published numbers that have
already been checked against the market.

```
SIDE       margin  = h_rating - a_rating + home_field            (ridge, lambda tuned)
TOTAL      total   = mu + off_h + def_a + off_a + def_h         (ridge, lambda tuned)
MONEYLINE  P(home) = Phi(margin / sigma) + half the tie mass
```

`sigma` is the out-of-sample standard deviation of the home margin estimated from the
walk-forward residuals of the same season, never from the week being predicted.

### The three defects this model had

| ID | What was wrong | How it was caught | Effect on the published number |
|---|---|---|---|
| L-01 | sample weight applied to the target only, not the design matrix | total MAE of 28.4 on a quantity averaging 44 is impossible | total MAE corrected |
| L-02 | the "this week" board selected `max(week)` among scheduled games | it published week 18 as the current card | board week corrected to 10 |
| L-03 | home and away ratings entered with the same sign, so the difference cancelled | `corr(fair, market)` was 0.024 — a model that does not move with the market is not measuring the spread | corr rose to 0.470; side MAE improved |

L-03 is the one worth remembering: the MAE alone looked plausible. The number that exposed it
was the correlation with the market, which is why that correlation is published next to the
accuracy on the Originated lines page.

### Tuning discipline

Lambda is chosen on **1999–2014 only** and frozen. Every published accuracy figure comes from
**2015–2026**, which the tuning never saw. A model tuned and scored on the same window is a
memory, not a forecast.

## 2. Signal is not staking

Two objects, scored separately:

* **Signal** — the picks. Hit rate on decided tickets (pushes excluded), a **per-ticket**
  break-even bar, a Poisson-binomial z against the sum of those bars, a 2,000-resample
  bootstrap interval, and a luck-trimmed hit rate with one-score games and blowouts removed.
* **Staking** — the money. ROI at a flat unit, profit and maximum drawdown under a
  5%-of-bankroll compounding plan, and a flag when a profit exists under one plan and not the
  other.

### Why the bar must be per ticket

A flat 52.38% bar is correct only for a −110 single. A +250 moneyline breaks even at 28.6%; a
two-leg −110 parlay at 27.44%. Applying 52.38% to everything produced two absurd results in an
earlier build:

* the parlay's 30.4% hit rate was scored z = −7.2 although it is three points **above** its own
  27.44% bar;
* the moneyline's 34.7% was scored z = −19.4 against a bar that applies to no moneyline ticket.

Both were caught by reading the row: a z of −7 next to a hit rate above break-even is a wrong
test, not a losing strategy. A second defect (B-02) paid parlay wins at single-leg odds, which
turned a +10.5% ROI into −40.7%. A third (B-03) ranked on ROI and put the weakest signal first.
All four are recorded on the Leaderboard page and in `data/lab/leaderboard.json`.

### Ranking rule

Rank by signal z, then by ROI. ROI is displayed and never ranks. A strategy with a positive ROI
and a z near zero is ranked below a strategy with a better z and a worse ROI, because the first
one's ROI is a staking artefact. This is the owner's requirement made mechanical.

## 3. Correlation: n or nothing

A correlation is a claim about a joint distribution, so each value carries:

* **n** — the paired observations actually used;
* the **source of both sides** of the pair;
* a 2,000-resample bootstrap interval;
* a 2,000-draw permutation p-value;
* a **status**: `MEASURED`, `TOO FEW` (n < 30) or `NOT SOURCED`.

The third status is the important one: a pair whose inputs are not sourced is published as a
gap even when the arithmetic would run. Three required pairs — prop legs, injury count vs
margin, cross-strategy profit — are in that state, each with the specific thing that would
close it.

## 4. The demotion gate

A live strategy returns to paper when **any** of these fires, evaluated from published numbers
on every build:

| ID | Trigger | Test |
|---|---|---|
| D-01 | signal decay | two consecutive rolling 30-ticket windows with z < 0 against the per-ticket bar |
| D-02 | staking break | maximum drawdown under the 5%-compounding plan exceeds the 25% cap |
| D-03 | price loss | mean CLV proxy negative over the last full window |
| D-04 | drift | last 100 decided tickets more than 2 standard errors below the promotion bar |

The gate must be able to fire against a profitable row, or it is decoration. On this snapshot
it does: the parlay shows +10.5% ROI and is demoted by D-02 (52.7% drawdown) and D-03.

## 5. What is deliberately not modelled

* **The injury effect on the line.** Depth is measured (37 certain replacements, 34 at the
  second string, 0 at the third); its effect on the score is not, because one week of injury
  data cannot identify it. Folding it in would produce a line that cannot later be shown to
  have used it well or badly.
* **Player props.** No reachable prop price or prop outcome. Published as `UNTESTED` with n = 0,
  never simulated.
* **True CLV.** No timestamp and no book on any price row, so "beat the close" is a proxy,
  labelled as one.
