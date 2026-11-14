# Executive Summary

**Prepared:** 2026-11-14 · **Data as of:** 2026 NFL season, Week 10 · **Status:** third round —
verified results feed, price-snapshot store, signal/staking split and the demotion gate published

---

## 1. The one-paragraph version

This release does the two things that a betting-strategy project usually skips: it **establishes a
verified factual base**, and it **refuses to publish a number it cannot source**. Thirty-two teams'
Week 10 standings, all 14 Week 10 games, 345 official injury-report rows and five clubs' depth charts
are transcribed with per-row links to the official page and mechanically re-checked by 2,944
integrity assertions. Against that base, the project publishes a complete specification for
originating lines, removing luck, pricing correlation and running a skill-based leaderboard — and
publishes **zero** prices, **zero** correlation values and **zero** strategy results, because the
licensed data those require does not exist in this repository. The honest gap is enumerated as 18
numbered decisions.

## 2. What is verified and published today

| Item | Count | Source (official) |
|---|---|---|
| Division standings rows | 32 teams, 8 divisions, 2 conferences | `nfl.com/standings/division/2026/REG` |
| Week 10 games | 14 (1 final, 13 scheduled) + 4 byes (CHI, DEN, PHI, TB) | `nfl.com/schedules/2026/REG/week/10/` |
| Official injury-report rows | 345 players across all 28 participating clubs | `nfl.com/injuries/league/2026/reg10` |
| Club depth-chart rows (pilot) | 5 clubs: BUF, SEA, DET, GB, BAL | each club's own `/team/depth-chart` |
| Derived starter-at-risk rows | 35 listed starters on the report; 8 of them ruled **Out** | join of the two rows above |
| Verified results feed | 137 completed 2026 finals, weeks 1–10; row diff 0 mismatches; standings arithmetic 32/32 | `nfl.com/schedules/2026/by-week/week-N` per row |
| Signal grade (outcome-only) | 84–49 (63.16%), z = 3.04, p = 0.0024 on 133 decided games | results feed × walk-forward model line |
| Price-snapshot store | 84 records (14 games × side/total/moneyline × open/close); market side blank by rule | `nfl.com/schedules/2026/by-week/week-10` + repo model |
| Replacement-depth distribution | 680 slots on the 2nd string, 8 on the 3rd, 0 on the 4th; 16 gaps flagged | club depth charts × league injury report |
| Correlations (official-only) | 988 pairs, every one with n = 32, sources on `www.nfl.com` only | `nfl.com/standings` + `nfl.com/stats/team-stats` |

Every row carries a working link. Where the official page prints nothing, the cell is blank and the
row says so. Nothing was inferred to fill a gap.

## 3. What is deliberately not published, and why

| Not published | Blocking reason |
|---|---|
| Market lines / market open-close | No licensed or league-published odds feed to source them from (Q-02, new Q-19); snapshot store ships blank and flagged |
| Edge / expected value / ROI | Same, plus no settlement rule adopted (Q-03); difference column is blank while the market cell is blank |
| Close snapshots for played games | The store went live after the Week 10 Thursday kickoff; recorded as post-hoc, never back-dated (F-14) |
| Leaderboard ROI / staking columns | No official price source, so no return can be settled; staking group is blank by rule |
| Points-per-injury impact weights | No licensed snap counts (Q-04) |
| Depth data for 1 club | Not yet captured (Q-14); 31 of 32 published |

A project that shows a plausible number in these cells is showing an invented number. The absence is
the feature.

## 4. The five findings that actually matter

1. **There is no league-wide official depth chart.** The NFL publishes none. Clubs publish their own,
   and Detroit and Green Bay print the word **"unofficial"** on the page. Any claim about 2nd-, 3rd-
   or 4th-string replacements must therefore be labelled a club self-report, not a league fact. This
   is the single biggest constraint on the availability requirement, and it is not widely stated.

2. **"Starter" is a definition you must choose, not a fact you can look up.** This release defines it
   mechanically — *printed in column 1 of the club's chart* — so the definition is auditable and can
   be re-run, rather than being an editorial judgement per player.

3. **A 55% hit rate over a season is not skill.** At −110 the break-even is 52.38%. A strategy hitting
   55.1% over 500 bets scores **z ≈ 1.22**, which is inside coin-flip range. The site shows this
   arithmetic so that a hot record cannot be mistaken for an edge.

4. **Parlay margin compounds.** At −110 one leg carries a 4.55% hold; five legs carry 20.75% — about 4.6×.
   And assuming independence across correlated legs misprices the ticket: two 50% legs with ρ = 0.30 have a
   joint probability of 0.325, so a book paying +264 is handing the bettor about 18.5%. That is exactly why
   books cap correlated legs. Prop combos must be priced from a joint distribution or not at all.

5. **Verification caught a real error of ours.** Arizona was first transcribed as 2–6; the official
   page prints 3–6 with .333. The arithmetic gate rejected the row, and the correction is documented
   publicly as flag F-08. The gate that found it is the reason to trust the other 31 rows slightly
   more — not the reason to stop checking.

## 5. The competition design in one screen

- **Four divisions** (singles, 2–3 leg parlays, same-game prop combos, single props) because the
  statistics genuinely differ.
- **Rank by `z_skill`**, not ROI, then penalise poor calibration and excess drawdown.
- **Effective sample size** `n_eff = n / (1 + (k−1)ρ̄)` stops correlated tickets from inflating evidence.
- **Seven gates**, in order, pre-registered. Failing Gate 0 means *unscored*, which is distinct from
  *failed*, and unscored never enters the board.
- **Champion requires two consecutive qualifying windows**; two failures demote; titles can be vacated.
- **Calibration is rewarded independently of profit**, so the board does not simply crown luck.
- **Season 0 is a paper league.** No money moves until funding, eligibility and jurisdiction are settled.

## 6. What the owner has to decide (in dependency order)

| Order | Decision | Why it is first |
|---|---|---|
| 1 | **Q-01** data licence, **Q-02** odds feed | Nothing quantitative can be scored without these two |
| 2 | **Q-05** the definition of "starter" | Unlocks the availability model's credibility |
| 3 | **Q-03** settlement rules, **Q-09** market scope | Makes a fair price gradeable |
| 4 | **Q-11** bankroll & staking, **Q-12** first scored window | Required by the risk and pre-registration gates |
| 5 | **Q-07/Q-08** rewards, eligibility, jurisdiction | Only needed once results exist to reward |
| 6 | **Q-14** 32-club depth coverage, **Q-17** refresh cadence | Scale and staleness |

The remaining questions (Q-04, Q-06, Q-10, Q-13, Q-15, Q-16, Q-18) are recorded in full on the
Decision Register page with what would settle each one. Round 3 added six more, all with the same
discipline — **Q-19** which price feed may fill the market columns, **Q-20** what job captures the
close snapshot at kickoff, **Q-21** which thresholds ratify the demotion gate, **Q-22** whether the
signal is graded against 50% or against price break-even, **Q-23** which of the two in-repo models
is the origination of record, **Q-24** how the results feed refreshes without a person reading
pages.

## 7. Reviewer's route through this release

1. **Flagged for Review** — 19 items, each with what is verified, what is unknown and what settles it.
2. **Decision Register** — 24 questions with known information and the blocking consequence.
3. **Suggestions** — 18 proposals with impact, effort, dependency and a reversible first step.
4. **Sources** — the verification tiers and every URL used, so any row can be re-checked by hand.
5. **Results feed** — 137 finals with per-row game links, then the signal grade computed from them.
6. **Snapshots & order** — open/close captures and the side → total → moneyline publication order.
7. **Data tables** — the evidence itself, one link per row.

## 8. Honest limitations of this release

- The injury report and schedule are a **single-week snapshot** and will be stale within days.
- Depth coverage is **31 of 32 clubs**; the last club's column is blank on purpose (F-03).
- The results feed for weeks 1–10 was read page by page this round; the scheduled refresh does not
  re-read it yet (Q-24, suggestion S-17) — a layout change on nfl.com would fail the new build
  checks loudly rather than corrupt the feed quietly.
- The market side of every line is blank. No official source publishes prices (Q-02/Q-19), so no
  ROI, CLV or difference exists anywhere on this site — by rule, not by omission.
- The signal grade (63.16% hit rate, z = 3.04) is measured on 133 decided games, well below the
  500-bet G1 threshold; it is published as a measurement, not as a promotion.
- Two in-repo models publish different Week 10 lines and neither has been designated the
  origination of record (Q-23, F-19).

## 9. What round 3 added

- **Verified results feed (requirement: verified results for backtests).** 137 completed 2026
  games read line by line from the NFL's own by-week pages, each row carrying its game-page and
  schedule-page links. Three checks run on every build: row diff against the league publishing
  mirror (137/137, 0 mismatches), league-standing arithmetic (32/32 clubs), and a source-URL audit
  that fails on any non-`nfl.com` link.
- **Signal metric.** The walk-forward model's side pick graded against those results:
  **84–49 (63.16%), z = 3.04, p = 0.0024** on 133 decided games (1 tie and 3 zero-line games
  excluded and named). Outcome-only — no price, no stake, no return — because no official price
  source exists.
- **Price-snapshot store (requirement: opening and closing numbers).** 84 records covering every
  market we originate × two stages. Our line is always recorded; the market line is blank and
  flagged until Q-19 resolves; a stage not captured in time keeps its status rather than being
  back-filled. The Week 10 Thursday game is marked post-hoc because the store went live after its
  kickoff (F-14).
- **Origination order + three columns (requirements: side → total → moneyline; fair / market /
  difference as separate columns).** 42 rows, sequences asserted to be exactly 1, 2, 3 per game.
  Difference = fair − market and stays blank while the market cell does.
- **Signal/staking split (requirement: lucky staking cannot mask bad signal).** The leaderboard now
  publishes two column groups; rank uses the signal group only, structurally. ST-11 (the model side
  pick) carries a populated signal row and blank staking columns, below G1 threshold on purpose.
- **Replacement depth (requirement: track depth, not just the fact).** The deficiency page now
  shows how deep each replacement runs — 680 second-string, 8 third-string, none fourth-string —
  plus the 16 starters on the report whose club chart names no next man (F-15, left unfilled).
- **Correlations from official numbers only (requirement: official sources + publish n).** All 988
  pairs audited on every build: integer n on every value (n = 32), p-value present, hosts limited
  to `www.nfl.com`, violations = 0. Third-party mirror correlations are excluded and labelled.
- **Demotion gate (requirement: live → paper).** Root gate **G8** with four pre-registered
  triggers, an immediate paper-flip action, and re-entry only through a fresh window — thresholds
  proposed, awaiting owner ratification (Q-21), inactive while nothing is live. Methodology:
  `docs/methodology/demotion-gate.md`.
