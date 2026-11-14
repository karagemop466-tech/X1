# Raw data — nflverse/nfldata

Files in this directory are verbatim copies of committed files from the **nflverse/nfldata** repository
(<https://github.com/nflverse/nfldata>), the open-source data project that mirrors official NFL sources
(NFL GSIS schedule/results feed, weekly club injury reports, Vegas closing lines as recorded by Sportsbook Review / Golden Ratings).

- Snapshot pulled: **2026-11-14** via `codeload.github.com/nflverse/nfldata/tar.gz/refs/heads/master` (repo `master` branch tip at pull time).
- Provenance/verification: each file's columns and sample rows were checked against the repo's `DATASETS.md` documentation (copied here as `DATASETS.md`).
- Downstream processed datasets must link every published row to an official/trusted page; nflverse is the *pipeline*, the official page is the *citation*.

## Files

| File | Contents | Upstream path |
|---|---|---|
| `games.csv` | All NFL games 1999–2026: date, teams, scores, spread_line, total_line, rest, roof, surface, weather, QBs, coaches, stadium | `data/games.csv` |
| `teams.csv` | Team metadata (abbreviations, names, colors, logos) | `data/teams.csv` |
| `standings.csv` | Weekly standings snapshots | `data/standings.csv` |
| `closing_lines.csv` | Closing lines (moneyline/spread/total) 2006– | `data/closing_lines.csv` |
| `initial_lines.csv` | Opening lines 2021– | `data/initial_lines.csv` |
| `win_totals.csv` | Preseason win totals 2003– | `data/win_totals.csv` |
| `officials.csv` | Game officials | `data/officials.csv` |

## Access notes (sandbox)

- GitHub release assets (e.g. weekly `injuries_2026.csv` from nflverse-data releases) are **not downloadable** from this sandbox — the redirect hosts `objects.githubusercontent.com` / `release-assets.githubusercontent.com` are blocked. Flagged as an environment limitation; injury data was instead transcribed from ESPN's league injury page (see `data/processed/injuries_2026_w10.json` for per-row source links).
- `raw.githubusercontent.com` is likewise blocked; committed repo files are fetched via `codeload.github.com` archives, which is allowed.
