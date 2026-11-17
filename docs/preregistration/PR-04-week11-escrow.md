# PR-04 — Week 11 pre-kickoff escrow: three markets, two total estimators, and the settlement ledger

**Registered:** 2026-11-17, by session `arena-9d8c298c-x1`. The commit that first adds this file is the
registration; `tools/build_preregistration.py` resolves that commit from git and stores the SHA-256 of this
file beside it, so an edit after the fact is detectable rather than deniable. The record this rule writes
was built at **2026-11-17T23:1xZ**, and the first Week 11 kickoff is **2026-11-19 8:15 PM ET**
(01:15 UTC on 2026-11-20), read from the official Week 11 schedule page at
<https://www.nfl.com/schedules/2026/by-week/week-11>. The builder aborts if that ordering is not true, so
"before kickoff" is a checked fact in the artefact, not a claim in this document.

**What this registration is, and is not.** PR-01 is a *backtest* of a rule (weeks 3-10) plus a pre-kickoff
shadow record frozen on 2026-11-16. PR-04 is not a re-run of PR-01 with better information and it is not a
revision of anything PR-01 wrote. PR-04 registers a **prospective escrow**: a record of what this repository
predicted for the 13 Week 11 fixtures, made before those fixtures kick off, in the three markets in the
order the owner's brief demands, and a ledger that scores that record against official finals **only when
an official page prints them**. Two numbers from the same game week therefore live side by side and are
never merged: PR-01's record (149-game corpus, recorded 2026-11-16) and this one (150-game corpus, recorded
2026-11-17). A reader can compare them; neither can be edited to flatter the other.

## Why an escrow rather than another model page

The brief's demand is exact: *"Two-Stage Skill Leaderboard (Proper-Score Qualification → Prospective
CLV/ROI Escrow)"*, and *"freeze versions and record forecasts before kickoff"*. A leaderboard cannot rank
skill on a backtest alone — that is what `tools/build_results_r3.py`'s `signal_grade` is, and it is
explicitly not leaderboard-eligible. What makes a skill claim prospective is a record that exists before
the games and cannot be edited afterwards. There was one such record (PR-01's, 2026-11-16) and the
Week 10 game inside it has already settled; nothing in this repository scores it, and nothing in this
repository holds a pre-kickoff record of the total for any Week 11 fixture at all. Both gaps are this
registration's subject.

## The rule, in full, before any Week 11 result exists

**Corpus.** The completed 2026 regular-season games as read by this repository: the 136 weeks 1-9 rows in
`data/results/_raw/reads.tsv`, plus that file's own 2026-11-12 row, plus the 13 Week 10 finals transcribed
on 2026-11-17 in `data/lab/reads/2026-11-17/week10_finals.tsv`. 150 games. The corpus is frozen for this
registration: no Week 11 result enters it.

**Ratings, unchanged from PR-01 and for one reason.** The rating function, the home edge and the
probability transform are the values frozen in `docs/preregistration/PR-01-shadow-baseline.md`
(`K = 2.0`, `H = 1.6`, `SIGMA = 13.5`). They are read from PR-01's constants at build time. A new
registration may inherit frozen constants; it may not quietly re-tune them, because the only thing that
separates a pre-registered model from a fitted one is that the constants were written down first.

```
raw(t)      = ( sum of (points_for - points_against) over the games t has played ) / games_played(t)
rating(t)   = raw(t) * n(t) / (n(t) + K)
margin(h,a) = rating(h) - rating(a) + H
p(h wins)   = Phi( margin(h,a) / SIGMA )
```

**Market 1 — side.** `fair_line_home = -round_half(margin)`, the model's own number, no vig, no market
comparison. **Market 2 — total, published twice.** The brief: *"Publish every model total twice until one
wins."* Two estimators are produced, and both are scored, and neither is preferred in the record:

```
total_A = mean over the corpus of (away_score + home_score)
            # the league-average total: what a margin model knows about scoring, which is nothing,
            # so it is published as the floor of this method rather than as an estimate of the game

LEAGUE  = mean points per team per game over the corpus
pts(t)  = ( n(t)/(n(t)+K) ) * mean_points_scored(t) + ( K/(n(t)+K) ) * LEAGUE
alg(t)  = ( n(t)/(n(t)+K) ) * mean_points_allowed(t) + ( K/(n(t)+K) ) * LEAGUE
total_B = ( pts(h) + alg(a) ) / 2 + ( pts(a) + alg(h) ) / 2
gap     = total_B - total_A
```

`total_B` is the one that can be wrong in a useful direction: it says something about these two clubs.
`total_A` says something about the league. The gap column is the whole point of publishing both; the two
are collapsed to one only by the walk-forward comparison in the settlement ledger, and the collapse needs
at least one full game week of settled games (13 here) before it is allowed to happen.

**Market 3 — moneyline.** The zero-vig American price implied by `p`, the same stated conversion PR-01 uses.
It is a translation of a probability, not a quote, and the artefact labels it as such.

**Order, enforced.** Rows carry `market_order` 1, 2, 3 — side, total, moneyline — and the builder aborts if
any game's three markets are not recorded in that order. The brief's *"Originate the side first, then the
total, then the moneyline"* is a build constraint here, not a style.

**Market line and residual.** `market_line` and `residual = fair − market` are blank on every row. This
repository has no licensed price source for 2026 (open question `Q-02`; the pinned third-party mirror prints
a spread and a total for all 13 of these fixtures and prints no score for any of them, which is measured in
`data/lab/reads/2026-11-17/feed-closure-measurement.json`). A blank is not zero and is not "we forgot": the
column exists, it is rendered as an em dash, and the reason is printed beside it. **No CLV and no ROI is
computed by this registration for that reason.** When a price policy is decided, the residual column fills
retroactively for the recorded games, because the fair line was recorded first — that is what the escrow is
for — and the artefact says which rows were filled in after the fact and which were recorded in advance.

**Settlement, and only this.** A row settles when an official NFL page prints the final score for that
fixture and this repository has transcribed that page, with its URL and its clock time. Nothing else
settles a row: not a third-party mirror, not a push notification, not a score that "everyone knows". Until
then the row reads `open`. The settlement ledger scores settled rows with proper scores against the same two
frozen benchmarks PR-01 uses (the 0.5 coin and the 0.55 home baseline), publishes `n` beside every aggregate,
and prints the luck panel (`realised wins − expected wins`, the standard deviation, and the z) beside the
skill number every time.

**No leaderboard entry.** Nothing produced under PR-04 is ranked against a strategy competing for a reward.
It qualifies for the second stage by being recorded before kickoff and by being scored on settled official
rows; it enters the first stage only as a proper-score row with `n` and an interval, and its backtest
neighbour (PR-01's, and `signal_grade`'s) never crosses into that table at all.

**Two-sided "what would change our mind", for this entry.**

| | the condition |
|---|---|
| **Would confirm** | `total_B` beats `total_A` on Brier-vs-outcome (the mean squared points error of the total, here) over at least one full settled game week (n ≥ 13), with the gap reported per fixture; and the side row's lower-bound Brier skill against the 0.55 home baseline stays positive as the week settles. |
| **Would refute** | `total_A` matching or beating `total_B` on two consecutive settled game weeks, which would mean a scoring model has nothing to offer over the league average and the total should be collapsed to the floor rather than "improved"; or a side-row skill lower bound below zero for two consecutive prospective weeks; or a luck-panel |z| > 2, in which case whatever the score says, the record is variance. |
| **Not evidence either way** | one settled game. The current state of the ledger is exactly that, and the ledger says so on its face. |

**Immutability.** `tools/lab/build_escrow.py` writes two files. The forecast record refuses to overwrite an
existing `game_id` — a forecast you can edit after kickoff is not a forecast — and the settlement ledger is
rebuilt from the record plus the official reads each time, so the *scoring* can be re-run as games settle
while the *prediction* cannot be touched. Re-running the builder on a settled week changes only the ledger.

**Limits, stated where they will be read.** The model is a shrunk point-differential average: no opponent
adjustment, no personnel, no venue, no rest, no weather, and the total is either a constant or a two-club
average. It is a baseline, and the site publishes it as one. The Mexico City fixture (Vikings at 49ers)
gets the 1.6-point home edge because the rule says so and the rule is frozen for this window; the official
fixture page prints `Location: MEXICO CITY`, `Stadium: ESTADIO BANORTE`, so the edge is applied to a club
that is not playing at its own stadium, and that is recorded in the artefact as a limit of the rule rather
than quietly corrected.
