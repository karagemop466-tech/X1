# COORDINATION.md — shared task board

Repo: `karagemop466-tech/X1`
Live site: GitHub Pages (deployed from `main`)

## Session registry

| Session ID | Branch | Status | Scope (files owned) | Last commit |
|---|---|---|---|---|
| `S1-d577959f` | `arena/d577959f-x1` | active | `COORDINATION.md`, `pipeline/**`, `.github/workflows/**`, `docs/**`, `site/**`, `scripts/**`, `data/**`, `README.md` | see git log |

> Note for other sessions: this repo started as a single 4-byte `README.md`. `S1-d577959f`
> is the founding session and owns the whole initial build (pipeline, site, workflows, docs,
> data). Other sessions must claim *new* files only, or log a request below.

## Task board

Legend: `unclaimed` · `in progress` · `done` · `needs review` (published on the
**Flagged for Review** page; does not block anything).

| # | Task | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| T1 | Coordination board + branch claim | done | S1-d577959f | `COORDINATION.md` | created 2026-11-14 |
| T2 | Repo review, line by line, with source links | in progress | S1-d577959f | `docs/repo-review.md`, `site/repo-review.html` | repo had 1 file at start |
| T3 | Requirements inventory (collect / organize / analyze) | in progress | S1-d577959f | `data/requirements.json`, `site/requirements.html` | |
| T4 | Suggestions register + decision-review workflow | in progress | S1-d577959f | `data/suggestions.json`, `site/suggestions.html` | |
| T5 | Open questions / missing-information discovery plan | in progress | S1-d577959f | `data/questions.json`, `site/questions.html` | |
| T6 | Executive summary | in progress | S1-d577959f | `site/index.html` | |
| T7 | Official-source data pipeline (no manual input; scheduled) | in progress | S1-d577959f | `pipeline/**`, `.github/workflows/data-refresh.yml`, `data/*.json` | source: nfl.com + official club sites |
| T8 | Injury tracking + depth/backup deficiency model | in progress | S1-d577959f | `pipeline/fetch_depth_injuries.py`, `data/injuries.json`, `data/depth_charts.json`, `site/injuries.html` | |
| T9 | Strategy lab: originate lines, validation gates, correlation, skill vs luck, leaderboard | in progress | S1-d577959f | `pipeline/model_*.py`, `data/strategies.json`, `site/strategy-lab.html`, `site/lines.html` | |
| T10 | Static site build (clean dashboard, subpages by category) | in progress | S1-d577959f | `site/**` | |
| T11 | Verification: every row sourced to an official link; blank + flag otherwise | in progress | S1-d577959f | `scripts/verify_site.py`, `site/flagged.html` | |
| T12 | GitHub Pages deploy + integration + PR to `main` + merge | unclaimed | S1-d577959f (final integration session) | `.github/workflows/pages.yml` | runs after T1–T11 |

## Claims log

- 2026-11-14 — `S1-d577959f` claims T1–T12 (founding build). No other session had claimed
  anything; the repo contained only `README.md`.

## Change requests against another session's files

_None yet._

## Handoffs

_None yet._

## Verification policy

1. Every data row carries `source_url` pointing at the official page it came from
   (nfl.com, or an official club site on `*.nfl.com` / a club domain).
2. If a value cannot be confirmed from an official source it is stored as `null` and
   gets `verified: false`, and is published on **Flagged for Review**.
3. Nothing is marked verified without a checked source link.
4. `python3 scripts/verify_site.py` must pass (row-level source coverage + internal
   link check) before the integration merge.
