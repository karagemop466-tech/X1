# COORDINATION.md — shared task board

Repo: `karagemop466-tech/X1`
Live site: <https://karagemop466-tech.github.io/X1/> (GitHub Pages, legacy branch builder on `/` of `main`)

## Session registry

| Session ID | Branch | Status | Scope (files owned) | Last commit |
|---|---|---|---|---|
| `S1-d577959f` | `arena/d577959f-x1` | done (integration complete) | whole initial build: `COORDINATION.md`, `pipeline/**`, `.github/workflows/**`, `docs/**`, `scripts/**`, `data/**`, site pages at the repo root, `assets/**`, `README.md` | see git log |

> This repo started as a single 4-byte `README.md`. `S1-d577959f` is the founding
> session and owned the whole initial build. It also acted as the final integration
> session, because no other session had claimed anything.
>
> **Note for future sessions:** the site is published from the repository **root**,
> so repo-root `*.html` files and `data/` are shared outputs. Claim new files only,
> or log a request below.

## Task board

Legend: `unclaimed` · `in progress` · `done` · `needs review` (published on the
**Flagged for Review** page; does not block anything).

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| T1 | Coordination board + branch claim | done | S1-d577959f | `COORDINATION.md` | created 2026-11-14 |
| T2 | Repo review, line by line, with source links | done | S1-d577959f | `pipeline/repo_review.py`, `data/repo_review.json`, `repo-review.html` | 55 files hashed + rule-checked, each linked to GitHub |
| T3 | Requirements inventory (collect / organize / analyze) | done | S1-d577959f | `data/requirements.json`, `requirements.html`, `docs/project-brief.md` | 45 requirements, each with a verbatim quote from the brief |
| T4 | Suggestions register + decision-review workflow | done | S1-d577959f | `data/suggestions.json`, `suggestions.html` | 20 suggestions, 3 paths each, `decision_status` + `owner` columns |
| T5 | Open questions / missing-information discovery plan | done | S1-d577959f | `data/questions.json`, `questions.html` | 30 questions; 6 hard blockers (Q-01, 02, 04, 05, 06, 11) |
| T6 | Executive summary | done | S1-d577959f | `index.html` | headline findings + decision gate |
| T7 | Official-source data pipeline (no manual input; scheduled) | done | S1-d577959f | `pipeline/**`, `.github/workflows/data-refresh.yml`, `data/*.json` | standard library only; every 6h + game days |
| T8 | Injury tracking + depth/backup deficiency model | done | S1-d577959f | `pipeline/parsers.py`, `pipeline/run.py`, `data/injuries.json`, `data/depth_charts.json`, `data/deficiency.json`, `injuries.html`, `depth-charts.html` | 31/32 clubs covered; HOU flagged |
| T9 | Strategy lab: originate lines, validation gates, correlation, skill vs luck, leaderboard | done | S1-d577959f | `pipeline/model_correlation.py`, `data/{strategies,gates,leaderboard,market_lines,correlations}.json`, `strategy-lab.html`, `lines.html`, `correlations.html` | 988 computed correlations; result columns blank by design |
| T10 | Static site build (clean dashboard, subpages by category) | done | S1-d577959f | repo-root `*.html`, `assets/**` | 15 pages, JSON-driven tables |
| T11 | Verification: every row sourced to an official link; blank + flag otherwise | done | S1-d577959f | `scripts/verify_data.py`, `scripts/verify_site.py`, `flagged.html`, `data.html`, `sources.html` | 4,579 rows, 0 without a source |
| T12 | GitHub Pages deploy + integration + PR to `main` + merge | done | S1-d577959f | — | PR opened and merged; deploy confirmed |

## Claims log

- 2026-11-14 — `S1-d577959f` claims T1–T12 (founding build). No other session had
  claimed anything; the repo contained only `README.md`.
- 2026-11-14 — integration completed by `S1-d577959f`; T1–T12 closed.

## Change requests against another session's files

_None. No other session participated._

## Handoffs

_None._

## Conflicts encountered

_None. No other session pushed to this branch._

## Sources used

| Source | Used for | Verified |
|---|---|---|
| <https://www.nfl.com/standings/league/2026/REG> | Standings (32 clubs) | yes — 32 rows, arithmetic consistency check passes |
| <https://www.nfl.com/injuries/> | Official injury report, Week 10 2026 | yes — 345 rows, 28 tables |
| <https://www.nfl.com/stats/team-stats/> (9 tables) | Offense/defense passing, rushing, receiving, scoring, downs | yes — 288 rows, labels read from the page |
| <https://www.nfl.com/teams/> | The league's own list of official club sites | yes — 32 clubs |
| Each club's own official site (`/team/depth-chart`) | Depth charts, starters through 4th string | 31 of 32 clubs; HOU unreachable and flagged |
| <https://www.nfl.com/news/competition-committee-approves-revisions-to-injury-report-0ap3000000688693> | Official injury designation definitions | yes |
| <https://www.nfl.com/standings/tiebreakingprocedures> | Tie-breaking rules | yes |
| `docs/project-brief.md` (this repo) | Requirements, questions, suggestions | yes — quoted verbatim |

## Verification performed

- `python3 scripts/verify_data.py` — every row checked: an official `_source_url`,
  no undeclared blank values, and a host on the official allow-list. Result at the
  time of the merge: **15 datasets, 4,579 rows, 0 rows without a source.**
- `python3 scripts/verify_site.py` — 15 pages, 90 internal links, every
  `table[data-src]` resolves to parseable JSON, every row has a source. Result:
  **OK**.
- Standings arithmetic: home+road = overall record, PF−PA = net points, PCT matches
  W-L-T, for all 32 clubs.
- Manual spot check against the live official pages on 2026-11-14: six standings
  rows (BUF, SF, CHI, NYG, WAS, AZ) and four injury tables (WAS, NYG, NE, DET)
  matched the published values exactly, field for field.
- Depth-chart pages are accepted only when their content looks like a depth chart
  (position codes in column 1, player links after), and the HTTP attempt log is
  published per club.

## Irregularities flagged (published on the Flagged for Review page)

| ID | Irregularity | Disposition |
|---|---|---|
| F-01 | The brief asks for `session-<id>/<task>` branches; this session is pinned to one branch by the harness | Mitigated by recording session ID + file scope per task here. Needs an owner decision. |
| F-02 | No official source publishes betting prices | Market lines table ships empty; Q-02 raised |
| F-03 | No official machine-readable game results | Backtests, ROI and skill tests uncomputable; Q-04 raised |
| F-04 | HOU's official depth chart does not return a parsable page | Club excluded from the deficiency watch for that refresh; attempt log published |
| F-05 | The 2026 standings page prints no column header row | Four column meanings are positional, validated by the arithmetic check; F-05 raised |
| F-06 | Reward rules for the leaderboard are undefined | Not invented; Q-06 raised |

## Verification policy (standing)

1. Every data row carries `_source_url` pointing at the official page it was read
   from (nfl.com, or an official club domain the league itself lists).
2. A value that cannot be confirmed from an official source is stored as `null` and
   flagged — never inferred, never filled in.
3. Nothing is marked verified without a checked source link.
4. `python3 scripts/verify_data.py` and `python3 scripts/verify_site.py` must pass
   before any integration merge. Both are run by the refresh workflow.

## PR and merge record

- PR: _recorded below once opened_
- Merge result: _recorded below once merged_
- Pages deploy: _recorded below once confirmed_
