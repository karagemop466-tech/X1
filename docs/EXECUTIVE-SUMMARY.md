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
- Depth coverage is **5 of 32 clubs**; the other 27 columns are blank on purpose.
- One transcription error was found by our own gate. A second independent pass (suggestion S-10) is
  the cheapest remaining trust improvement, and it has not been done.
- Three other agent sessions touched this repository concurrently; their divergent boards are
  preserved on their branches and the audit is on the Flagged page (F-07).
- No model has been fit, so no claimed signal in the methodology section has been empirically
  supported. They are hypotheses with named tests, which is what a hypothesis is supposed to be.

---

# Executive Summary — second round addendum (2026-11-14, session `arena-1d3600f8-x1`)

The first-round summary above is preserved verbatim. Several of its "deliberately not published"
rows changed state this round — because the missing piece was built, not because the rule was
relaxed.

## What changed

| First round said | Second round state |
|---|---|
| No results feed; ROI not computable | **Verified results feed now exists**: 137 settled 2026 games (Weeks 1–10 through TNF), every row sourced to its official nfl.com game page, double-entry checked against the official standings — 32/32 clubs match on PF/PA and W-L-T, league totals 6,291 = 6,291, zero mirror disagreements. ROI is now computed from official outcomes (`data/results/roi_summary.csv`): **nothing is positive at the assumed −110**; model spread MAE 10.05 pts on verified results. |
| No price snapshots | **Price-snapshot store exists** (`data/price_snapshots/`): opening + closing capture slots for all 56 originated markets (14 games × side/total/moneyline), an append-only capture log, and a recorder tool. Opening quotes do not exist in any permitted source — blank and flagged (Q-02). Closing captures are the third-party mirror benchmark, labelled unverified on every row. |
| Correlation values not published | **15 official-only correlations published** with n, r, permutation p, Fisher CI and row-level official sources (`data/analysis/correlations_official.csv`). Mirror-based values remain visible but quarantined as non-official reference. |
| Leaderboard rankings withheld | The official-only board is still unranked (correct — no official prices yet), but the leaderboard now separates **signal from staking** (`data/leaderboard_signal_staking.csv`): final grade = min(signal, staking); 0 of 16 mirror-window strategies are rankable; a lucky staking run cannot mask a bad signal. |
| Depth tracking = starter vs backup | **Depth of the replacement is now tracked and published**: of 189 on-report starters, replacements sit at 2nd string (168), 3rd string (3), or unreadable (18, flagged, never inferred). Per-team, per-unit, per-status aggregates with sources (`data/analysis/replacement_depth.json`). |
| Demotion = one sentence | **Demotion gate G8 defined** (six mechanical triggers, action, re-entry, logging, authority; `data/gates.json`, `docs/methodology/demotion-gate.md`). D4/D5 switch on automatically when the price store gains captures. |

## The standing honest position

1. **The model is a screen, not a price.** On verified 2026 results nothing beats break-even at
   −110. This is published, not hidden.
2. **No official source publishes betting prices.** Every price cell is blank-and-flagged or
   labelled third-party. Q-02 (a licensed price feed) remains the single highest-leverage decision
   (suggestion S-A on the suggestion board).
3. **Nothing is ranked on luck.** The min(signal, staking) rule and the G8 demotion gate are wired;
   the board is honestly empty of promotable strategies.
4. **Verification is double-entry.** Every new feed is cross-checked against an independent official
   table; every table row on the site links to the page it came from (`tools/verify_app.py`: 5,784
   rows, 0 unsourced).


---

# Executive Summary — third round addendum (2026-11-14, session `arena-600e6009-x1`)

The second-round addendum above is preserved as written. This round adds what it uniquely
produced; where the same requirement was built by a parallel round, both artefacts are kept and
labelled rather than one being dropped.

## What this round added

| Requirement | This round's artefact | Relationship to the second round's |
|---|---|---|
| Verified results feed | Third independent transcription of all 137 finals (`data/results/_raw/reads.tsv` → `tools/build_results_r3.py`), three checks per build: row diff vs the publishing mirror (137/137, 0 mismatches), standings arithmetic (32/32), source-URL audit | Cross-checks the T16/N2 feeds rather than replacing them |
| Signal metric (price-independent) | Model side pick vs official result: **84–49 (63.16%), z = 3.035, p = 0.0024, n = 133** (1 tie, 3 zero-line games excluded and named), baseline 0.50 stated because no price exists | Complementary: the round-2 ROI table grades against an assumed −110; this grade needs no price at all |
| Price-snapshot store | 84 records (14 games × side/total/moneyline × open/close) with a capture-status vocabulary (`recorded`, `pending_kickoff`, `captured_post_final`, `not_captured_before_kickoff`) — a stage missed in time keeps its status, never a borrowed value | Same requirement, stricter rule: every market cell blank (no mirror close), statuses published on `app/snapshots.html` |
| Origination order + three columns | 42 rows, sequences asserted to be exactly 1, 2, 3 per game (side → total → moneyline); fair / market / difference as separate columns, difference blank while market is | Coexists with `app/origination.html`; the assertion lives in `tools/build_origination.py --check` |
| Signal / staking split | Official-basis board (`data/leaderboard_signal_staking_official.json`): ST-11 populated on signal only (n = 133), staking columns blank by rule, `rank_basis = signal_only` | Complements the mirror-basis T18 board; both are on `app/leaderboard.html` |
| Replacement depth | Distribution view: 680 slots on the 2nd string, 8 on the 3rd, 0 on the 4th, plus 16 starters on the report whose club chart names no next man (F-15, left unfilled) | Complements the per-slot store on `app/replacement-depth.html` |
| Official-only correlations | Audit of all 988 published pairs: integer n on every value (n = 32), p present, hosts limited to `www.nfl.com`, violations = 0, re-run on every build (`tools/build_round3.py --check`) | Independent check over the same discipline the round-2 15-pair table applies |
| Demotion gate | Adopted round-2's G8 (six triggers, `docs/methodology/demotion-gate.md`) as the register of record — this round's proposed duplicate G8 was dropped in favour of the richer, active one | Nothing discarded: the stronger definition wins the path |
| Decision registers | **Q-19…Q-24** (price feed for the snapshot store, close capture job, G8 ratification, signal baseline, origination of record, results refresh), **S-13…S-18** (six reviewable proposals), **F-14…F-19** (post-hoc Thursday captures, 16 unnamed replacements, 3 zero-line games, the tie, ARI/AZ alias, two-model disagreement) | Root registers were untouched by the earlier rounds; these are additive |

## Still open after this round

- **Q-19 / Q-02** — no official price source: market lines, differences, CLV and ROI stay blank everywhere, by rule.
- **Q-21** — this round asked for explicit ratification of demotion thresholds; the register of record is round-2's G8 (D1–D6, `data/gates.json`), whose D4/D5 stay inactive until a price feed exists.
- **Q-23** — two in-repo models publish different Week 10 lines; neither is designated the origination of record yet (F-19).
- **Q-24 / S-17** — the results feed is verified but not yet re-read by the scheduled refresh.
