# data/raw/nflverse — source data provenance (merged record)

Files in this directory are verbatim copies of committed files from **nflverse/nfldata**
(<https://github.com/nflverse/nfldata>, `master` branch, snapshot **2026-11-14**), the open-source
project that mirrors official NFL sources (NFL GSIS schedule/results feed, weekly club injury
reports, market lines as recorded by sportsbook-tracking feeds).

Two parallel sessions fetched the same upstream files via different reachable methods; both copies
are byte-identical where they overlap and both provenance records are preserved here.

## Acquisition methods used (both documented)

1. **codeload tarball** (`codeload.github.com/nflverse/nfldata/tar.gz/refs/heads/master`) — session
   `arena/61ce8500-x1`: `games.csv`, `teams.csv`, `standings.csv`, `closing_lines.csv`,
   `initial_lines.csv`, `win_totals.csv`, `officials.csv`, `DATASETS.md`.
2. **GitHub contents/blob API** (`api.github.com`) — session that built the line-origination model:
   adds `trades.csv`, `rosters.csv`.

## Files and verified coverage (span verified by scanning each file's season values)

| File | Rows | Verified coverage | Contents | Upstream path |
|---|---|---|---|---|
| `games.csv` | 7,548 | **1999–2026** (2026 through Week 18) | One row per game: scores, week, rest, market spread/total/moneylines, weather, roof, surface, expected QBs, coaches, stadium | `data/games.csv` |
| `closing_lines.csv` | 20,490 | **2006–2018** (verified: game_id year span) | Moneyline/spread/total closing lines per game side | `data/closing_lines.csv` |
| `initial_lines.csv` | 1,088 | **2021 only** | Opening lines (WSGT) | `data/initial_lines.csv` |
| `teams.csv` | — | historical | Team metadata incl. conference/division, ID mappings | `data/teams.csv` |
| `standings.csv` | — | historical | Computed standings by season/week | `data/standings.csv` |
| `trades.csv` | 4,975 | 2002–2026 | Player/pick trades | `data/trades.csv` |
| `rosters.csv` | 28,617 | **2006–2019 (stale)** | Weekly rosters | `data/rosters.csv` |
| `win_totals.csv` | 576 | **2003–2020** | Preseason win totals | `data/win_totals.csv` |
| `officials.csv` | — | historical | Game officials | `data/officials.csv` |
| `DATASETS.md` | — | — | Upstream data dictionary (column conventions) | `DATASETS.md` |

Corrections vs earlier drafts: an earlier provenance note claimed closing lines ran 2006–2026 and
opening lines 2021–2026; scanning the actual files shows **closing 2006–2018, opening 2021 only,
win totals 2003–2020**. The `games.csv` per-game `spread_line`/`total_line` columns do cover
1999–2026 and are the basis for all 2026 analytics; the discrete line files are older.

## Role in this project

- `games.csv` is the base for every computed value in `data/processed/` (analytics, correlations,
  Elo ratings, model lines) and the lab pages — per-row "computed" links point to
  `scripts/build_data.py`.
- Market lines embedded in games.csv are **bookmaker market data, not official NFL data**; they are
  used as the benchmark for the project's own originated lines, never presented as truth.
- `rosters.csv` staleness is why 2026 backup/depth names are left blank and flagged (see the site's
  Flagged for Review pages and `data/processed/flagged_for_review.json`).

## Access notes (sandbox)

- GitHub release assets (e.g. weekly `injuries_2026.csv` from nflverse-data releases) are **not
  downloadable** here — the redirect hosts `objects.githubusercontent.com` /
  `release-assets.githubusercontent.com` are blocked. Injury data was therefore transcribed from
  ESPN's league injury page (`data/processed/injuries_2026_w10.json`, per-row source links).
- `raw.githubusercontent.com` is blocked; committed repo files come via `codeload.github.com`
  archives or the `api.github.com` contents API — both used successfully.
