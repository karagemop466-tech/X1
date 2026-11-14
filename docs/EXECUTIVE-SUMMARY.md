# Executive Summary

**Prepared:** 2026-11-14 · **Data as of:** 2026 NFL season, Week 10 · **Status:** first evidence-bearing release

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

Every row carries a working link. Where the official page prints nothing, the cell is blank and the
row says so. Nothing was inferred to fill a gap.

## 3. What is deliberately not published, and why

| Not published | Blocking reason |
|---|---|
| Fair lines / our own prices | No licensed historical odds feed to benchmark against (Q-02) |
| Edge / expected value | Same, plus no settlement rule adopted (Q-03) |
| Correlation values | No joint-outcome dataset; a 0.10 correlation needs ~780+ paired obs (Q-10) |
| Leaderboard rankings | No logged forecasts, no scored window (Q-12) |
| Points-per-injury impact weights | No licensed snap counts (Q-04) |
| Depth data for 27 clubs | Not yet captured (Q-14) |

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
Decision Register page with what would settle each one.

## 7. Reviewer's route through this release

1. **Flagged for Review** — 12 items, each with what is verified, what is unknown and what settles it.
2. **Decision Register** — 18 questions with known information and the blocking consequence.
3. **Suggestions** — 12 proposals with impact, effort, dependency and a reversible first step.
4. **Sources** — the verification tiers and every URL used, so any row can be re-checked by hand.
5. **Data tables** — the evidence itself, one link per row.

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
