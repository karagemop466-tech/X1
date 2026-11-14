# Open Questions — Information Needed Before Decisions

Purpose: a single, reviewable list of the questions, information, and answers that must be resolved **before** strategy selection, sizing, or implementation decisions are made. Each row states what we already have (with source), what is missing, and a concrete way to discover the missing piece. Nothing on this page is decided; each item ends with a proposed decision owner.

**Status legend:** OPEN = unanswered · PARTIAL = partly answered below · DECIDED = recorded decision (none yet).

## Q1. Rewards: what does "rewards for top-performing strategies" mean?

| Field | Content |
|---|---|
| Status | OPEN |
| What we have | Leaderboard scoring design exists (points, tiers, anti-gaming rules) — [leaderboard.html](leaderboard.html) |
| What's missing | Whether rewards are real money, account credit, points, or privileges; who funds them; payout cadence |
| How to discover | Decision maker states intent; if real money: define pool, per-tier split (proposal: 50/30/20 Champion/Challenger/Analyst), and funding source |
| Blocks | Payout logic, strategy-tier eligibility, anti-gaming enforcement |
| Owner | Decision maker (you) |

## Q2. Bankroll and risk policy

| Field | Content |
|---|---|
| Status | OPEN |
| What we have | Validation-gate math defines minimum sample sizes and Kelly-fraction sizing rules — [validation-gates.html](validation-gates.html) |
| What's missing | Actual bankroll size, max drawdown tolerance, max % of bankroll per bet and per slate, legal wagering jurisdictions available to you |
| How to discover | Decision maker provides the numbers; system converts them into hard unit rules in the bet ledger |
| Blocks | Any real-money sizing; leaderboard reward conversion |
| Owner | Decision maker |

## Q3. Odds feed for live lines and CLV tracking

| Field | Content |
|---|---|
| Status | PARTIAL |
| What we have | Historical closing lines 2006–2026 and opening lines 2021–2026 via nflverse (verified convention, mean \|diff\| 0.23 pts) — [methodology.html](methodology.html) |
| What's missing | A **live, in-season** odds feed (opening → closing per book) to log CLV at pick time and to detect stale lines |
| How to discover | Evaluate: (a) nflverse weekly release assets (blocked in this sandbox, fine in GitHub Actions), (b) The Odds API / comparable paid feed, (c) manual book snapshot log; choose one and record its license |
| Blocks | CLV scoring (leaderboard's 40% weight), line-shopping, model-vs-market alerts |
| Owner | Decision maker + integration session |

## Q4. Play-by-play / player-stat data for props

| Field | Content |
|---|---|
| Status | PARTIAL |
| What we have | Game-level data only (scores, spreads, totals, weather). Player prop fair-line generation and **player-level correlation values are not computable yet** — flagged, not faked — [props-and-parlays.html](props-and-parlays.html) |
| What's missing | Weekly play-by-play and/or official player stats (targets, carries, air yards, usage) for 2026 |
| How to discover | nflverse weekly pbp release via GitHub Actions (nflverse-data releases), nflverse/ngs-data release, or NFL.com "Game Book" official PDFs per game; pick a source, verify one week against NFL.com box scores before use |
| Blocks | Player-prop combos, same-game parlay correlation measurement, EPA-based ratings upgrade |
| Owner | Integration session, with decision maker approval of source |

## Q5. Depth charts to name backups (2nd/3rd/4th string)

| Field | Content |
|---|---|
| Status | PARTIAL |
| What we have | Position-group impact flags for every Week 10 team (HIGH/MEDIUM/LOW) from the source-linked injury report — [injuries.html](injuries.html) |
| What's missing | Named expected backups per injured starter (deliberately left blank — no official depth-chart source verified in this environment) |
| How to discover | Official club depth charts (each team's site / NFL.com team pages) or GSIS weekly depth-chart release; verify 3 teams line-by-line before adopting |
| Blocks | Backup-QB and backup-line group value quantification |
| Owner | Second verification session (task T8) |

## Q6. Weather inputs for Week 10 lines

| Field | Content |
|---|---|
| Status | PARTIAL |
| What we have | Historical final game conditions in nflverse games.csv (roof, temp, wind) — computed wind-unders baseline |
| What's missing | Forecast values for this week's outdoor games (MIA@IND, LAR@ARI, SEA@LV, SF@DAL, PIT@CIN, etc.) |
| How to discover | NFL gamebooks (official, posted ~90 min before kickoff), NOAA forecast for stadium locations; log forecast vs final condition to calibrate a weather model |
| Blocks | Weather overlays on model totals/spreads |
| Owner | Weekly line desk (future session) |

## Q7. Model upgrade path beyond Elo v0

| Field | Content |
|---|---|
| Status | PARTIAL |
| What we have | Elo v0 with documented parameters and honest failure modes (e.g., BUF@NYJ model −16.2 vs market −8.5) — [lines-model.html](lines-model.html) |
| What's missing | Decision on next model tier: (a) margin-based ratings + schedule adjustment, (b) EPA/play-by-play ratings (needs Q4), (c) ensemble |
| How to discover | Walk-forward backtest protocol is already defined; run candidate models on 2015–2025, score on 2026 out-of-sample; adopt only if gates pass |
| Blocks | Making model lines bettable; leaderboard eligibility |
| Owner | Strategy session |

## Q8. Leaderboard governance

| Field | Content |
|---|---|
| Status | PARTIAL |
| What we have | Scoring weights, minimum samples, anti-gaming rules, audit/ledger schema — [leaderboard.html](leaderboard.html) |
| What's missing | Your sign-off on weights (CLV 40 / ROI 30 / calibration 15 / stability 15), scoring cadence (weekly), dispute policy, who audits |
| How to discover | Review leaderboard.html; approve or amend; record decision here |
| Blocks | Reward payouts; strategy onboarding |
| Owner | Decision maker |

## Q9. Automation of the weekly cycle

| Field | Content |
|---|---|
| Status | OPEN |
| What we have | One-shot pipeline (`scripts/build_data.py`) + static site; manual ESPN injury transcription (documented) |
| What's missing | Scheduled refresh: GitHub Actions to pull nflverse weekly data, re-run pipeline, rebuild site; a maintained injuries source for automation |
| How to discover | Add a weekly Actions workflow (cron) calling the same scripts; verify one automated run end-to-end against manual check before trusting it |
| Blocks | Weekly leaderboard operation at scale |
| Owner | Integration session |

## Q10. Risk, legality, and responsible use

| Field | Content |
|---|---|
| Status | OPEN |
| What we have | This is analysis software; no wagering occurs in the system. US problem-gambling helpline 1-800-GAMBLER is referenced site-wide |
| What's missing | Your jurisdiction and age eligibility confirmation; any compliance constraints on rewards |
| How to discover | Decision maker confirms; keep the disclaimer on every page |
| Blocks | Real-money features |
| Owner | Decision maker |
