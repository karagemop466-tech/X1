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
| T1 | Repo scaffolding + COORDINATION.md + data ingest (nflverse committed CSVs via codeload) | done | sess-a17c3f-x1 | `COORDINATION.md`, `data/raw/**` | nflverse/nfldata @ master snapshot 2026-11-14; provenance in data/raw/nflverse/README.md |
| T2 | Week 10 2026 injury report — all 32 teams, transcribed from ESPN league injury page, row-linked sources | done | sess-a17c3f-x1 | `data/processed/injuries_2026_w10.json` | 491 rows / 32 teams, each row links its ESPN player page; 18 status-vs-comment mismatches flagged (verbatim, never corrected); NFL.com injury cross-check recommended (T8) |
| T3 | Schedule/results + standings + market lines (2026 season) | done | sess-a17c3f-x1 | `data/processed/schedule_2026.json`, `standings_2026.json`, `week10_games.json` | Computed standings cross-checked vs official NFL.com league standings: **32/32 teams match** (games through 2026-11-14); spread convention verified vs closing_lines.csv (6138/6736 within 0.6 pts, mean \|diff\| 0.23 pts) |
| T4 | Analytics: ATS/trends/correlation backtests from nflverse games.csv (1999–2026) | done | sess-a17c3f-x1 | `scripts/build_data.py`, `data/processed/analytics.json` | n=7,104 games; correlation values published on site; backup-QB signal corrected for look-ahead bias (49.8% = no edge) — worked example in validation gates |
| T5 | Strategy research docs: own-line generation, signals, validation gates, luck removal, leaderboard + rewards, props/parlays/correlation | done | sess-a17c3f-x1 | `docs/strategies.md`, `docs/validation-gates.md`, `docs/leaderboard.md`, `docs/props-and-parlays.md`, `docs/correlation-analysis.md` | Elo v0 own-line engine built (0/8 gates passed — informational only) |
| T6 | Injury/backup deficiency analysis (starters out → 2nd/3rd/4th-string impact flags) | done | sess-a17c3f-x1 | `data/processed/deficiency_flags_2026_w10.json` | HIGH/MEDIUM/LOW flags per Week 10 team; named backups deliberately blank (no verifiable depth-chart source in environment) — flagged |
| T7 | Open questions (decision blockers) + Suggestions pages | done | sess-a17c3f-x1 | `docs/open-questions.md`, `docs/suggestions.md` | 10 open questions with discovery plans; 12 suggestions pending review |
| T8 | *Reserved for a second session* — independent line-by-line verification pass of T2/T3 data + NFL.com cross-checks | unclaimed | — | — | Must not edit T2/T3 files; log findings in COORDINATION.md log |
| T9 | Final integration: build site, verify links, re-verify data, PR to main, merge, confirm GitHub Pages deploy | in progress | sess-a17c3f-x1 | site build outputs, `index.html`, GitHub Pages | Site built (14 pages); internal link check PASS; PR + merge pending |

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
| 2026-11-14 03:20 | sess-a17c3f-x1 | T1–T7 marked done. Verification summary: standings 32/32 vs [NFL.com](https://www.nfl.com/standings/league/2026/REG); spread convention 6138/6736 vs closing_lines.csv (mean \|diff\| 0.23 pts); injuries 491 rows transcribed verbatim from [ESPN](https://www.espn.com/nfl/injuries) with 18 status/comment mismatches + 12 roster-assignment flags + environment limits (34 flags total) published on flagged.html. Irregularities do NOT block release per policy. Backup-QB look-ahead-bias correction documented in validation-gates.md (worked example). |
| 2026-11-14 02:45 | sess-a17c3f-x1 | Board created. Claims T1–T7, T9. Repo was empty (stub README only). GitHub Pages already enabled on repo from `main:/` (verified via GitHub API `repos/karagemop466-tech/X1/pages`). |
