# Control baselines — pre-registered definition

**Status:** pre-registered. This file is committed *before* any control result is computed.
The git commit that adds it is the registration. Changing a rule after that commit requires a new
registration (a new commit with a new `rule_version`), and the change is published, not hidden.

**Question.** How well does a bet that needs no model do on the same games a strategy is judged on?
If a strategy cannot beat these controls, its result is luck or the price, not skill.

## Universe (fixed)

- Source: `data/lab/upstream/games.csv`, from the nflverse/nfldata repository (community mirror,
  **not** an official NFL source). Archive pinned in `data/lab/upstream/_pin.json`
  (archive SHA-256 `0c93b5ec…`, file SHA-256 `7d791bb4…`).
- Games: `game_type == REG`, seasons **2019 through 2025** (complete seasons only), with both scores
  present and a non-empty `spread_line`.
- The 2026 season is **not** in the registered universe: it is incomplete and is shown descriptively only.

## Conventions (checked against the data before registration)

- `spread_line` is from the **home** team's perspective. A positive value means the **home team is
  favoured**. Check: over the 1,871 games in the universe, home teams with a positive line won 66.3%
  of the time (n = 1,118), home teams with a negative line won 33.3% (n = 753), and the slope of the
  home margin on the line is 1.05.
- Home margin `m = home_score − away_score`. Home **covers** when `m − spread_line > 0`. A tie with
  the line, `m − spread_line = 0`, is a **push**.
- The **favourite** is the home team when `spread_line > 0`, otherwise the away team. A line of exactly
  zero would be undefined; none occurs in the universe.
- The book, the timestamp and the price of `spread_line` are **not stated** by the mirror. It is used as
  a benchmark, labelled as such, never as an official price.

## Control A — random picks

- For each game, pick home or away with probability 1/2, independently.
- Random generator: Python `random.Random(20261115)`. Replications: **1,000**, each covering the full universe.
- Reported: the mean ATS win rate across replications, the 2.5th and 97.5th percentiles, and the share
  of replications whose win rate is at least the favourites-only rate (Control B).
- Pushes are excluded from every win-rate denominator and counted separately.

## Control B — favourites only

- Always bet the favourite against the spread (ATS).
- Also reported: the straight-up favourite win rate. No price is needed for that figure.

## Confidence intervals

- Win rates carry a **Wilson 95% interval** on the non-push count.
- The break-even rate at −110 is `110/210 = 52.38%`. This is arithmetic, not an observed price.

## ROI

- ROI at −110 is **assumed**, labelled as assumed on every page that shows it. No official price exists
  in the repository (open question Q-02). It is shown only to make the break-even visible.

## Gate that uses the controls

A leaderboard strategy is said to **beat the controls** on a window only when all of these hold on
the same games:

1. its ATS win rate is above the point estimate of Control A **and** of Control B; and
2. the lower bound of its Wilson 95% interval is above 52.38%.

Failing either condition does not remove a strategy from the leaderboard. It is recorded as "does not
beat control", with the numbers.

## Limits

- Benchmark values come from a community mirror, not from an official NFL page. They are flagged on the
  page and in the Flagged for review list.
- Favourites are defined by the mirror's spread. A different spread source could change Control B.
- A pass against these controls is not a validation. It is only the first of the eight gates in
  `docs/methodology/validation-gates.md`.
