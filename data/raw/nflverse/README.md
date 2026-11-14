# data/raw/nflverse — source data provenance

Files in this directory were downloaded on **2026-11-14** via the GitHub contents/blob API
(`api.github.com`, the only GitHub host reachable from this sandbox) from:

- Repo: https://github.com/nflverse/nfldata (`master` branch, `data/` directory)
- License: MIT (as stated in the nflverse/nfldata repository)

| File | Size | Contents | Coverage |
|---|---|---|---|
| games.csv | 2.19 MB | One row per NFL game: scores, week, rest days, market spread/total/moneylines, weather, roof, surface, expected QBs | 1999–2026 (2026 through Week 18) |
| closing_lines.csv | 0.94 MB | Moneyline/spread/total closing lines per game side | 2006–2018 (stale — not updated since; flagged) |
| initial_lines.csv | 45 KB | Opening lines (WSGT) | 2021+ |
| teams.csv | 91 KB | Team metadata incl. conference/division | historical |
| standings.csv | 57 KB | Computed standings by season | historical |
| trades.csv | 283 KB | Player/pick trades | 2002–2026 |
| rosters.csv | 1.6 MB | Weekly rosters | **stale (ends 2019)** — flagged, not usable for 2026 depth charts |
| win_totals.csv | 13 KB | Preseason win totals | 2003–2020 (stale) — flagged |

## Role in this project
- **games.csv is the trusted-secondary numeric source** used to (a) cross-verify every
  NFL.com standings row (32/32 exact match on W-L-T, PF, PA — see docs/review/repo-review.md),
  and (b) fit/validate the line-origination model (`code/build_lines.py`).
- Market lines embedded in games.csv are **bookmaker market data, not official NFL data**;
  they are only used as a benchmark for the project's own originated lines, never presented as truth.
- Refresh: re-run the fetch (see `code/build_reference_data.py` header) or download from the
  nflverse releases; note release assets live on `objects.githubusercontent.com`, which this
  sandbox cannot reach — the in-repo CSVs are the canonical copies here.

## Known staleness flags (also on the site's Flagged for Review page)
1. `rosters.csv` ends at the 2019 season → official 2026 depth charts cannot be derived here.
2. `closing_lines.csv` ends at the 2018 season → long-run CLV studies limited; per-game
   spread/total lines in `games.csv` (2019+) are used instead.
3. `win_totals.csv` ends at 2020 → no 2026 preseason win totals in-repo.
