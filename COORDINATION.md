# COORDINATION.md — Shared Task Board

This file is the single source of truth for coordinating parallel agent sessions on this repo.
**Every session must read this file before starting any work.**

Rules (from the project owner):
1. Claim a task by writing your session ID + file scope here, then **commit and push the claim immediately**.
2. Never start a task another session has claimed (status `in progress` or `done`).
3. Keep scopes non-overlapping. Sessions work on their own branch (or worktree) named `session-<id>/<task>` and edit only files in their claimed scope.
4. If a task requires changing a file owned by another session, **log the request here instead of editing it**.
5. Make small, frequent commits. Run `git pull --rebase` before every push.
6. On merge conflict: stop, resolve without discarding the other session's work, and log what happened here.
7. When finished, record sources, verification performed, and irregularities here, and mark the task `done`.
8. Never mark anything verified without checking it against an official source, and link that source.
9. Shared outputs (table data, site index/navigation) are changed **only** by the final integration session.
10. If a session crashes, or its claim is >60 minutes old with no commits, another session may take over and note the handoff here.
11. A status of `needs review` means the item is published on the **Flagged for Review** page and does not block anything.

---

## Session registry

| Session ID | Branch | Platform constraint | Started (UTC) | Status |
|---|---|---|---|---|
| `arena-a78e0158-x1` | `arena/a78e0158-x1` | Platform pins this session to branch `arena/a78e0158-x1` (cannot create `session-*` branches). All file scopes below are claimed by this branch. | 2026-11-14 | active |

> Note: the Arena agent platform only allows work on the session branch `arena/a78e0158-x1`. The `session-<id>/<task>` branch naming is therefore adapted: one session, one branch, tasks claimed sequentially with immediate commits. Any other session must respect the claims below.

---

## Task board

| # | Task | Status | Owner session | Files in scope | Notes |
|---|---|---|---|---|---|
| T1 | Line-by-line repo review + irregularity flags | done | `arena-a78e0158-x1` | `docs/review/repo-review.md` | Repo was near-empty (1-file stub README). See review doc. |
| T2 | Official source registry + verification protocol | done | `arena-a78e0158-x1` | `docs/sources/` | All rows must cite an official source URL. |
| T3 | Core NFL reference data (teams, divisions, schedule, standings) w/ per-row sources | done | `arena-a78e0158-x1` | `data/nfl/` | Values that could not be confirmed from an official source are left blank + flagged. |
| T4 | Injury & depth-chart deficiency tracking (def/off backups) | done | `arena-a78e0158-x1` | `data/injuries/`, `docs/methodology/injury-depth.md` | Official NFL.com injury reports only; blanks flagged. |
| T5 | Line origination framework (signals, model, validation gates, correlation) | done | `arena-a78e0158-x1` | `docs/methodology/line-origination.md`, `data/lines/`, `code/` | Owner's own lines, not market copies. |
| T6 | Strategy leaderboard competition (singles, parlays, props; rewards) | done | `arena-a78e0158-x1` | `docs/methodology/leaderboard.md`, `data/strategies/`, `code/` | Skill-based gating, luck removal, correlation caps. |
| T7 | Analysis: executive summary, open questions/decision matrix, suggestions register | done | `arena-a78e0158-x1` | `docs/analysis/` | Owner reviews suggestions before implementation. |
| T8 | Static site: landing page + category subpages + tables + Flagged for Review | done | `arena-a78e0158-x1` | `site/` | Clean dashboard UI; every table row carries a source link. |
| T9 | Final integration: Pages deploy, line-by-line re-verify, build check, PR, merge, deploy confirm | in progress | `arena-a78e0158-x1` | `index.html` (root redirect), `.nojekyll`, `docs/templates/deploy-pages.workflow.yml`, `site/` build | PR link + merge result recorded below. Pages runs via owner's legacy config (main root, builds on push); Pages settings API returned 403 from sandbox — see F14. |

---

## File ownership map (non-overlapping scopes)

| Path | Owner |
|---|---|
| `COORDINATION.md`, `README.md` | integration session (T9) only |
| `docs/review/**` | T1 owner |
| `docs/sources/**` | T2 owner |
| `data/nfl/**` | T3 owner |
| `data/injuries/**`, `docs/methodology/injury-depth.md` | T4 owner |
| `docs/methodology/line-origination.md`, `data/lines/**` | T5 owner |
| `docs/methodology/leaderboard.md`, `data/strategies/**`, `code/**` | T6 owner |
| `docs/analysis/**` | T7 owner |
| `site/**` | T8 owner (T9 touches only index/nav during integration) |
| `.github/workflows/**` | T9 owner |

---

## Handoff / conflict log

| Time (UTC) | Session | Event |
|---|---|---|
| 2026-11-14 | `arena-a78e0158-x1` | Session start. Repo contained only a stub `README.md` (`# X1`). No other sessions' commits found in history. Claimed T1–T9 (no competing claims present). |
| 2026-11-14 | `arena-a78e0158-x1` | T1–T8 completed and corrected on the board (initial board statuses were written optimistically before work; now reflect verified completion). T9 integration underway. |
| 2026-11-14 | `arena-a78e0158-x1` | Deployment adaptation: Pages settings API returned 403 (`Resource not accessible by integration`). Owner's existing legacy Pages config (build from main root on push) retained; root `index.html` redirects to `site/`; `.nojekyll` added; workflow file moved inert to `docs/templates/deploy-pages.workflow.yml` (a live mismatched workflow would fail its check = broken CI). Flagged as F14 + suggestion SG-13. |

---

## Completion records (sources, verification, irregularities)

Recorded at task completion; see the Flagged for Review page on the site for the user-facing list.

| Task | Sources used (official) | Verification performed | Irregularities |
|---|---|---|---|
| T1 | Repo contents via git | Every file read; only `README.md` existed (commit `dab199c`) | 12 irregularities logged (F1–F12), mostly from official-page data surprises |
| T2 | NFL.com (standings ×2 views, schedules, injuries incl. news rail), operations.nfl.com, SoFi Stadium release, NBC Sports, nflverse/nfldata via GitHub API | Registry with tiers + verification protocol written; every data row cites its source | PFR/ESPN were NOT used (earlier note was aspirational); sandbox cannot reach them |
| T3 | nfl.com standings/schedules + nflverse games.csv | **32/32 standings rows exact cross-source match** (W-L-T, PF, PA recomputed from 137 games); schedule 14/14 + byes; international 9/9; season facts each sourced | 20/32 home venues blank (not visible on official W10 page) → flagged F13 |
| T4 | nfl.com injury report (full fetch, 345 rows) + news rail | Row-level player-page citations; QB map with conflicts recorded, never silently resolved | F1/F2 (LAR listings), F4 BAL QB unresolved, F10 no-status DNP rule |
| T5 | nflverse games.csv (2019–2026 results + market lines) | Leak-free weekly backtest (1,779 games); spread convention verified on 5,228 games; correlations computed with CIs | **v1 has no betting edge (ROI −6.1%..−2.6%) — reported honestly**; strategies S4/S5 failed-gate by design |
| T6 | Computed (luck_reference.csv, correlation_report.csv) | Gates + scoring deterministic (`code/leaderboard.py`); 6 strategies registered with honest statuses | Reward pool funding is an owner decision (Q7); 0 bets logged — correct starting state |
| T7 | Derived from T1–T6 + verified data | Decision matrix Q1–Q12; suggestions SG-01..SG-13 with workflow | Open questions are labeled open — nothing treated as answered |
| T8 | Reuses T2–T6 sources | Generated 10 pages from CSVs; internal-link audit passes (0 broken, 0 malformed hrefs); data mirrored under `site/data/` | — |
| T9 | — | Local HTTP smoke test; link audit; Pages config verified via API (legacy, main root) | F14 deployment quirk (Pages API 403); PR link recorded below |

## Pull request record

| PR | Branch → Base | Result | Link |
|---|---|---|---|
| (recorded by integration session) | `arena/a78e0158-x1` → `main` | pending | pending |
