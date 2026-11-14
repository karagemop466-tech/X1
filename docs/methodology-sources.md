# Methodology & Sources — Verification Record

## Primary sources used this session

| # | Source | Used for | Link | Retrieved |
|---|---|---|---|---|
| 1 | **nflverse/nfldata** — committed CSVs (`games.csv`, `teams.csv`, `standings.csv`, `closing_lines.csv`, `initial_lines.csv`, `win_totals.csv`) | All historical games 1999–2026 (scores, spreads, totals, rest, roof, wind, QBs), market lines, team metadata | [github.com/nflverse/nfldata](https://github.com/nflverse/nfldata) | 2026-11-14 (master tarball via codeload) |
| 2 | **NFL.com official standings** — league view, 2026 regular season | Cross-check of computed standings | [nfl.com/standings/league/2026/REG](https://www.nfl.com/standings/league/2026/REG) | 2026-11-14 |
| 3 | **ESPN NFL injuries page** — "NFL Injury Status - 2026 Season" | Week 10 injury report, all 32 teams (491 rows), each row link to ESPN player page quoting club reports | [espn.com/nfl/injuries](https://www.espn.com/nfl/injuries) | 2026-11-14 |
| 4 | **ESPN scoreboard** (site.api.espn.com — reachable via the agent's page-fetch tool) | Week 10 slate confirmation incl. Munich international game; team records spot-check | [espn.com/nfl/scoreboard](https://www.espn.com/nfl/scoreboard) | 2026-11-14 |
| 5 | **nflverse/nfldata DATASETS.md** | Column conventions (spread_line sign convention) | [DATASETS.md](https://github.com/nflverse/nfldata/blob/master/DATASETS.md) | 2026-11-14 |

## Verification performed (line by line)

| Check | Method | Result |
|---|---|---|
| spread_line sign convention | Compared 6,736 spread entries in games.csv against explicit per-team closing lines in closing_lines.csv | 91.1% agree within 0.6 pts; mean \|diff\| 0.23 pts (residual = book/timing variation) — convention confirmed; residual logged as a flag |
| Standings | Computed W-L-T from every played 2026 game in games.csv; compared to NFL.com official league standings (games through 2026-11-14) | **32/32 teams match exactly** (incl. the NYG-WAS tie: W5, 27-27) |
| Spread/total results | `home_cover = home_margin − spread_line > 0`; over/under vs total_line; convention documented in schedule JSON | implemented in script |
| Injury report | Transcribed all 32 ESPN team tables verbatim (name, position, est. return, status, comment, player URL); 491 rows | 18 status-vs-comment mismatches flagged (never corrected); 10+ 2026 player-team assignments flagged for independent confirmation |
| Tie game detection | Scanned all played 2026 games for equal scores | W5 NYG 27 @ WAS 27 found; standings cross-check confirms NFL.com matches |
| No-inference policy | Script leaves `model_total_hint`, `expected_backup_names` blank; blanks registered as flags | 34 flags published on [flagged.html](flagged.html) |

## Reproduction

```
python3 scripts/build_data.py    # rebuilds every processed JSON from raw CSVs + transcribed injuries
python3 scripts/build_site.py    # rebuilds the static site from processed JSON + docs/*.md
```

## Environment limitations (documented, not hidden)

- GitHub **release-asset downloads are blocked** in this sandbox (`objects.githubusercontent.com`, `release-assets.githubusercontent.com`) → nflverse weekly injury release and play-by-play releases are NOT used; ESPN page transcription used instead. Options to unblock recorded in open-questions Q4/Q5.
- `raw.githubusercontent.com` blocked; committed repo files fetched via `codeload.github.com` archives.
- ESPN/NFL.com reachable only through the agent's page-fetch tool, not the sandbox shell.

## Disclaimer

This repository is data-analysis and research software. It does not accept wagers, process payments, or recommend bets. If you wager, do so legally and only with money you can afford to lose. Problem gambling help (US): **1-800-GAMBLER**.
