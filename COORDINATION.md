# Coordination board

Session ID: `arena/0c2fcfa1-x1` (current branch: `arena/0c2fcfa1-x1`).

**Role:** final integration session. This session owns the shared outputs — the
site index, the navigation, the shared stylesheet and the published dataset
directory — which are only changed during final integration.

| Task | Status | Owner | File scope |
|---|---|---|---|
| Baseline repository review and NFL decision-support site, sourced research framework, executive summary, and review queue | done | arena/6f377170-x1 | `COORDINATION.md`, `README.md`, `index.html`, `assets/`, `research.html`, `validation.html`, `availability.html`, `questions.html`, `review.html`, `.github/workflows/pages.yml` |
| Official-source data pipeline, derived depth and correlation datasets, static site generator and strict source-link verifier | in progress | arena/0c2fcfa1-x1 | `src/nflx/`, `data/nfl/`, `pages/`, `_site/`, `assets/site.css`, `.github/workflows/refresh-data.yml`, `.github/workflows/probe-*.yml`, `COORDINATION.md`, `README.md`, root `index.html` |

## Non-overlap map

The `arena/d577959f-x1` session owns `pipeline/`, root-level `data/*.json` and
`diag/`. This session deliberately works in `src/nflx/` and `data/nfl/` so the
two pipelines cannot overwrite each other's output. Only the final integration
step touches `index.html`, the navigation and the shared stylesheet.

## Log

- 2026-11-14 — Merged `origin/main` into `arena/0c2fcfa1-x1` after moving the
  untracked local `COORDINATION.md` aside (it would otherwise have been
  overwritten). Merge commit base `066915e`. No repository file was overwritten.
- 2026-11-14 — Established that the agent sandbox cannot reach NFL hosts
  (`curl` returns code `000`) but GitHub Actions runners can. Verified by probe
  workflow `probe-nfl-egress`: all five official endpoints returned HTTP 200
  with the expected payloads. The data collection therefore runs in CI.
- 2026-11-14 — Built a stdlib-only collector (`src/nflx/`) covering the
  official injury report, standings, schedule, season player statistics and
  the official Game Book PDF (lineups, substitutions, did-not-play, inactive
  list, officials, weather, full box score).
- 2026-11-14 — Built the derived datasets: depth deficiency (unavailable
  starter → replacement string) and correlation (measured relationships with
  sample sizes and Fisher-z confidence intervals, plus an explicit list of
  what cannot be measured without a licensed price feed).
- 2026-11-14 — Built the static site generator and a strict verifier that
  parses the rendered HTML and fails the deployment if any populated table row
  lacks an official source link, if any external link is off-allow-list, if
  any internal link is broken, or if any page is orphaned. All seven checks
  pass on the current build.
