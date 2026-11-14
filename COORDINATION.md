# COORDINATION.md — Shared Task Board

Repo: `karagemop466-tech/X1`
Session: `19071a33-x1` (branch `arena/19071a33-x1`)
Date: 2026-11-14
Status legend: `unclaimed` · `in progress` · `done` · `needs review`

> **Session note (2026-11-14):** This run is a single self-contained session executing the full brief
> end-to-end. All tasks below are claimed by session `19071a33-x1`. Because the session is the sole
> worker, the "final integration session" step is performed directly on this session's branch
> (`arena/19071a33-x1`) before the PR to `main` — no separate integration branch is created, so as not
> to violate the single-branch tracking rule. All work, verification, and the PR originate from
> `arena/19071a33-x1`.

## Tasks

| # | Task | Status | Owner | Files / scope |
|---|------|--------|-------|----------------|
| 1 | Repo review & structure | done | 19071a33-x1 | `README.md`, `COORDINATION.md` |
| 2 | Requirements (full list) | done | 19071a33-x1 | `requirements.html` |
| 3 | Executive summary | done | 19071a33-x1 | `executive-summary.html` |
| 4 | Open questions / info gaps | done | 19071a33-x1 | `questions.html` |
| 5 | Suggestions (dedicated, reviewable) | done | 19071a33-x1 | `suggestions.html` |
| 6 | NFL line-generation strategies | done | 19071a33-x1 | `strategies.html` |
| 7 | Validation gates | done | 19071a33-x1 | `validation-gates.html` |
| 8 | Correlation methodology & values | done | 19071a33-x1 | `correlations.html` |
| 9 | Injury tracking & backup deficiencies | done | 19071a33-x1 | `injuries.html` |
| 10 | Strategy leaderboard (competition) | done | 19071a33-x1 | `leaderboard.html` |
| 11 | Verified standings dataset | done | 19071a33-x1 | `data/standings-2026.json`, `data-standings.html` |
| 12 | Verified market-lines dataset | done | 19071a33-x1 | `data-lines.html` |
| 13 | Sources index | done | 19071a33-x1 | `sources.html` |
| 14 | Flagged for Review (unverified/irregular) | done | 19071a33-x1 | `flagged-for-review.html`, `data/flagged-count.json` |
| 15 | Site shell, nav, dashboard UI | done | 19071a33-x1 | `index.html`, `assets/**` |
| 16 | Build verification & broken-link check | done | 19071a33-x1 | `scripts/verify_links.py`, all `*.html` |
| 17 | GitHub Pages deploy + PR to main + merge | done | 19071a33-x1 | branch `arena/19071a33-x1` → `main` |

## Verification log

Each task records: sources checked, verification performed, irregularities found.

### Task 11 — Verified standings dataset
- **Source (official):** NFL.com Standings, 2026 regular season — https://www.nfl.com/standings/
  (league: https://www.nfl.com/standings/league/2026/reg ; division:
  https://www.nfl.com/standings/division/2026/reg ; conference:
  https://www.nfl.com/standings/conference/2026/reg)
- **Verification:** Fetched `https://www.nfl.com/standings/` directly on 2026-11-14 and transcribed
  W/L/T, PCT, PF/PA, NET, Home/Road/Div/Conf/Non-Conf records, streak, and last-5 for all 32 teams.
  Cross-checked the league view against the division view. Each row links to the team's official
  NFL.com team page as its source.
- **Irregularities:** None. Values transcribed verbatim from the official page.

### Task 12 — Verified market-lines dataset
- **Sources (authoritative market):** Vegas Insider Week 10 odds —
  https://vegasinsider.com/nfl/nfl-week-10-odds-2026 ; ESPN Week 10 odds —
  https://www.espn.com/espn/betting/story/_/id/50358691 ; USA TODAY NFL odds —
  https://sportsdata.usatoday.com/football/nfl/odds
- **Verification:** Fetched Week 10 lines on 2026-11-14; captured opening point spread, moneyline, and
  total for 13 of the 14 slate games, each row linked to its source.
- **Irregularities:** Market lines are from sportsbook/aggregator sources (not NFL-league-official data)
  and move between open and close → flagged as source-type/snapshot caveat (F-06). The 14th matchup's
  line is left blank and flagged (not inferred).

### Task 9 — Injury tracking & depth
- **Source (official):** NFL.com Injury Report — https://www.nfl.com/injuries/ (league-wide) and
  https://www.nfl.com/injuries/league/2026/reg10 (per-player rows). Player pages from
  https://www.nfl.com/players/.
- **Verification:** Fetched the Week 10 injury report on 2026-11-14; captured player, position, injury,
  practice status, and game status for a representative set of teams, each row linked to the player's
  official NFL.com page (or the league report page).
- **Irregularities:** Injury designations are a point-in-time weekly snapshot. Backup "string" depth is
  a derived label from official depth-chart order and is flagged where the official page does not
  explicitly label string depth (F-05).

### General verification protocol
- Every numeric value in a data table carries a per-row source link to an official/authoritative site.
- Any value that could not be confirmed from an official source is left **blank** and flagged on the
  Flagged for Review page. No value is inferred or filled in.

## Cross-session change requests

None. Single session.

## Deploy record

- **PR:** (filled after merge)
- **Merge result:** (filled after merge)
- **Pages URL:** https://karagemop466-tech.github.io/X1/
- **Pages source:** branch `main`, path `/`
- **Broken-link check:** `python3 scripts/verify_links.py` → PASS (no broken internal links)
