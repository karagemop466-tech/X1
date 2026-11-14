# COORDINATION.md — Shared Task Board

This file is the single coordination point for all agent sessions working on this repo.
**Read it before starting any task. Claim a task by writing your session ID here, then commit and push the claim immediately.**

- Repo: `karagemop466-tech/X1`
- Project: NFL data collection, verification, analysis, and strategy development (see `docs/executive-summary.md`)
- Shared outputs (site index/navigation, combined table data) are changed only by the final **integration session** once all other tasks are done.
- Unverified values and irregularities never block a merge — they are published on the site's **Flagged for Review** page.

---

## Session registry

| Session ID | Branch | File scope | Status | Last active (UTC) | Notes |
|---|---|---|---|---|---|
| `sess-a17c3f-x1` | `arena/61ce8500-x1` | `docs/*`, `data/*`, `scripts/*`, `site/*`, `index.html` (root), `README.md` | active | 2026-11-14 02:45 | Founding session: created board, claims T1–T7 + T9 (integration). Sandbox restriction: release-asset downloads (`objects.githubusercontent.com`, `release-assets.githubusercontent.com`) are blocked; raw.githubusercontent.com blocked; ESPN/NFL.com reachable only via Arena `fetch_page` tool, not bash. Session therefore works on its assigned Arena-tracked branch instead of a `session-<id>/<task>` branch (Arena binds sessions to branches); isolation is enforced by file scope. |

---

## Task board

| Task | Description | Status | Owner | Files | Notes |
|---|---|---|---|---|---|
| T1 | Repo scaffolding + COORDINATION.md + data ingest (nflverse committed CSVs via codeload) | in progress | sess-a17c3f-x1 | `COORDINATION.md`, `data/raw/**` | nflverse/nfldata @ master, commit-pinned; see data/raw/nflverse/README.md |
| T2 | Week 10 2026 injury report — all 32 teams, transcribed from ESPN league injury page, row-linked sources | in progress | sess-a17c3f-x1 | `data/processed/injuries_2026_w10.json` | ESPN source page + per-player links; NFL.com cross-check on sample |
| T3 | Schedule/results + standings + market lines (2026 season) | in progress | sess-a17c3f-x1 | `data/processed/schedule_2026.json`, `data/processed/standings_2026.json` | Derived from nflverse games.csv/standings.csv; ESPN cross-check |
| T4 | Analytics: ATS/trends/correlation backtests from nflverse games.csv (1999–2026) | in progress | sess-a17c3f-x1 | `scripts/*.py`, `data/processed/analytics.json` | All computed values labeled with generation script + source |
| T5 | Strategy research docs: own-line generation, signals, validation gates, luck removal, leaderboard + rewards, props/parlays/correlation | in progress | sess-a17c3f-x1 | `docs/strategies.md`, `docs/validation-gates.md`, `docs/leaderboard.md`, `docs/props-and-parlays.md`, `docs/correlation-analysis.md` | |
| T6 | Injury/backup deficiency analysis (starters out → 2nd/3rd/4th-string impact flags) | in progress | sess-a17c3f-x1 | `data/processed/deficiency_flags_2026_w10.json` | Position-group flags; named backups only where depth chart is source-verified, else blank + flagged |
| T7 | Open questions (decision blockers) + Suggestions pages | in progress | sess-a17c3f-x1 | `docs/open-questions.md`, `docs/suggestions.md` | |
| T8 | *Reserved for a second session* — independent line-by-line verification pass of T2/T3 data + NFL.com cross-checks | unclaimed | — | — | Must not edit T2/T3 files; log findings in COORDINATION.md log |
| T9 | Final integration: build site, verify links, re-verify data, PR to main, merge, confirm GitHub Pages deploy | pending | sess-a17c3f-x1 | site build outputs, `index.html`, GitHub Pages | Runs after T1–T7 done |

**Status meanings:** `unclaimed` → free to claim. `in progress` → claimed, being worked. `needs review` → published on Flagged for Review page, does not block. `done` → finished, sources + verification recorded in the Log below.

---

## Rules

1. Never start a task another session has claimed.
2. Keep file scopes non-overlapping. If you need a file another session owns, **log the request here** instead of editing it.
3. Small, frequent commits. Run `git pull --rebase` before every push.
4. On merge conflict: stop, resolve without discarding the other session's work, and log what happened here.
5. Never mark anything verified without checking it against an official source; record the source link.
6. If a session's claim is >60 minutes old with no commits, any other session may take over the task and note the handoff here.
7. Every table row on the site carries a source link to an official/trusted page. Values that cannot be confirmed are left **blank** and flagged as unverified — never inferred.

---

## Log (append-only, newest first)

| When (UTC) | Session | Event |
|---|---|---|
| 2026-11-14 02:45 | sess-a17c3f-x1 | Board created. Claims T1–T7, T9. Repo was empty (stub README only). GitHub Pages already enabled on repo from `main:/` (verified via GitHub API `repos/karagemop466-tech/X1/pages`). |
