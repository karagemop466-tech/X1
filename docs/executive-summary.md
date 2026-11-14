# Executive Summary — X1 NFL Intelligence & Strategy Project

*Snapshot date: 2026-11-14 · Season: 2026 NFL regular season, Week 10 of 18 · All computed values link to the script that produced them.*

## 1. Purpose

Build a verified data foundation and a strategy development system for **originating our own NFL betting lines**, evaluating **single bets, parlays, and player-prop combos** in a **leaderboard competition**, where every strategy must **pass validation gates** before it is eligible for rewards. The system tracks **injuries and roster deficiencies** (starters out, 2nd/3rd/4th-string replacements) as a first-class signal.

## 2. What exists today (this session)

| Component | Status | Where |
|---|---|---|
| Raw historical data (all NFL games 1999–2026 with scores, spreads, totals, rest, weather, QBs) | ✅ loaded from nflverse/nfldata committed CSVs | [data/raw/nflverse](https://github.com/nflverse/nfldata) |
| 2026 schedule, results, market lines (137 of 272 games played) | ✅ built + verified | `data/processed/schedule_2026.json` |
| Official standings cross-check | ✅ **32/32 teams match** NFL.com league standings (games through 2026-11-14) | [NFL.com standings](https://www.nfl.com/standings/league/2026/REG) |
| Week 10 injury report, all 32 teams (491 player rows), each row source-linked | ✅ captured from ESPN league injury page | [ESPN NFL Injuries](https://www.espn.com/nfl/injuries) |
| Backup/deficiency impact flags per Week 10 game | ✅ built (position-group level; named backups intentionally blank — see [Flagged](flagged.html)) | `data/processed/deficiency_flags_2026_w10.json` |
| Historical analytics + correlation values (computed, 1999–2026) | ✅ built | `data/processed/analytics.json` |
| Own-line engine v0 (Elo power ratings → model spreads vs market) | ✅ v0 built; **not yet validated** — do not bet | `data/processed/model_lines_w10.json` |
| Strategy framework, validation gates, leaderboard + rewards design | ✅ documented | [strategies.html](strategies.html), [validation-gates.html](validation-gates.html), [leaderboard.html](leaderboard.html) |
| Open questions & suggestions for the decision maker | ✅ documented | [open-questions.html](open-questions.html), [suggestions.html](suggestions.html) |

## 3. Key verified facts about the 2026 season (as of 2026-11-14)

- **Records (official, [NFL.com](https://www.nfl.com/standings/league/2026/REG))**: BUF 7-1 and SF 7-1 lead; CHI 7-2 and DEN 7-2; DET/KC/MIN/PIT/CIN/JAX 6-2; winless LAC 0-8; PHI 2-7 (seven-game losing streak); NYG 5-3-1 and WAS 3-5-1 (Week 5 tie, NYG 27 @ WAS 27).
- **Week 10 slate (14 games)**: Thursday WSH@NYG already played (WAS 24-21). Sunday includes the Munich, Germany international game, NE @ DET at FC Bayern Munich Stadium. Byes: DEN, CHI, PHI, TB.
- **Quarterback situations that change line math** (all from the source-linked injury report): PHI QB Jalen Hurts on IR (blood clots in lungs; out for season per report); BAL QBs **1, 2 and 3** (Lamar Jackson, Tyler Huntley, Skylar Thompson) all on injured reserve; SEA QB Sam Darnold ruled out Week 10; MIN QB Kyler Murray ruled out Week 10; ARI QB Gardner Minshew out for season (UCL surgery); NYG QB Jaxson Dart on IR (knee surgery); GB RB Josh Jacobs out (finger surgery) and DE Micah Parsons ruled out; LAR WRs Puka Nacua and Davante Adams on IR; DET missing CB D.J. Reed, S Kerby Joseph and C Cade Mays for the Munich game.

## 4. Key computed findings (1999–2026, n=7,104 regular-season games unless noted)

| Finding | Value | Note |
|---|---|---|
| Home teams win straight up | **55.9%** | baseline home-field edge |
| Favorites cover the spread | **48.5%** (n=7,074) | market efficiency baseline: naive favorite betting loses |
| Home favorites cover / road favorites cover | **46.9%** (n=4,564) / **51.5%** (n=2,510) | road favorites have historically covered more — descriptive only, not yet a validated strategy |
| Games go OVER the total | **48.9%** | |
| OVER rate when outdoor wind ≥ 10 mph | **44.7%** (n=1,805) | classic weather lean toward unders |
| Road team with 7 extra days rest (off bye vs short-week home) — home covers | **43.2%** (n=287) | road side covers 56.8%; z≈2.3; **provisional** — multiple-testing caveat applies |
| Backup-QB teams cover (look-ahead-bias-free) | **49.8%** (n=2,156) | **no edge** — the naive version (42.3%) was pure look-ahead bias; see validation gates worked example |
| Cross-game independence: weekly home-cover variance ÷ binomial expectation | **0.99** (473 weeks) | game outcomes across a slate behave independently → parlay math can use multiplication |
| corr(market spread, actual home margin) | **0.431** | market line is a moderately strong margin predictor |
| corr(margin, total) / corr(\|margin\|, total) | **0.017 / 0.075** | side and total nearly uncorrelated |
| P(home cover) vs P(home cover \| over) | **47.5% vs 47.8%** | spread & total legs near-independent at game level |

All values are **computed by [`scripts/build_data.py`](https://github.com/karagemop466-tech/X1/blob/main/scripts/build_data.py)** from `data/raw/nflverse/games.csv` — no external values, no inference.

## 5. Our own lines — v0 model vs market (Week 10)

The Elo engine (K=20, margin-of-victory weighted, home field 1.75 pts calibrated from 1999–2026 data) produces fair spreads for every Week 10 game. Largest model–market disagreements (model minus market, home-team line, points):

| Game | Market (home) | Model (home) | Δ |
|---|---|---|---|
| BUF @ NYJ | −8.5 | −16.2 | **−7.7** |
| JAX @ TEN | −10.5 | −15.5 | **−5.0** |
| SF @ DAL | −4.5 | −7.5 | **−3.0** |
| PIT @ CIN | +3.5 | +1.0 | **−2.5** |
| SEA @ LV | −6.5 | −9.1 | **−2.6** |

**Warning:** v0 model has **passed zero validation gates**. Large disagreements right now mean "model is crude", not "market is wrong". The path from model to bettable line is defined in [validation-gates.html](validation-gates.html) and requires out-of-sample tracking that has not happened yet.

## 6. What we deliberately did NOT do

- No values inferred anywhere. Where a fact could not be confirmed from an official/trusted source, the field is **blank and flagged** — e.g., named backup players (no verifiable depth-chart source in this environment), totals model (not built), live odds (no odds feed).
- No "verified" label on anything computed-only. Computed values are labeled computed, with script + raw file links.
- 34 irregularities are logged and published on the [Flagged for Review](flagged.html) page rather than silently "fixed".

## 7. Decisions needed before strategy selection

Nine decision blocks (bankroll, odds feed, rewards definition, prop data source, depth charts, weather, leaderboard governance, automation, risk policy) are itemized with "what we have / what's missing / how to find it" in [open-questions.html](open-questions.html). Suggestions for improving decision-making are collected in [suggestions.html](suggestions.html).

**Responsible-use note:** this project is research and analysis, not betting advice. No wagering occurs in this system. If you bet, do so legally and only with money you can afford to lose (US: 1-800-GAMBLER).
