# COORDINATION — Shared Task Board

Repository: `karagemop466-tech/X1` · Live site (GitHub Pages, from `docs/` on `main`): see **Pages** section at the bottom.

## Session and branch policy

- Active session ID: `c39d8541`
- Working branch for this session: `arena/c39d8541-x1` (branched from `main` @ `dab199c`).
- Arena policy for this session allows work on one branch only, so the `session-<id>/<task>` branch-per-task pattern in the project brief is **not used**. Task claims are recorded in this file instead. Scopes below do not overlap, so no two tasks touch the same file.
- Status legend: `unclaimed` · `in progress` · `done` · `needs review` (published on the **Flagged for Review** page; does not block anything).

## Task board

| ID | Task | Status | Owner (session) | Files / scope |
|----|------|--------|-----------------|---------------|
| T1 | Repo review — line-by-line check of repo state, irregularities | done | c39d8541 | `README.md` (read only), `COORDINATION.md` |
| T2 | Official 2026 data: standings, Week 10 schedule, Week 10 injury report | done | c39d8541 | `data/standings_2026.csv`, `data/schedule_2026_week10.csv`, `data/injuries_2026_week10.csv`, `data/sources.csv` |
| T3 | Strategy research: own line model, validation gates, correlations, parlays | needs review | c39d8541 | `analysis/`, `data/strategy_*.csv`, `data/parlay_*.csv`, `data/data_checks.json` |
| T4 | Injury depth analysis (starter vs backup, offense and defense) | needs review (blocked on official depth-chart source) | c39d8541 | `data/depth_*.csv` (not yet created) |
| T5 | Site build: landing page, category subpages, tables | done | c39d8541 | `scripts/build_site.py`, `docs/` |
| T6 | Suggestions and questions/information-gap register (decision items, no changes implemented) | done — awaiting owner choice | c39d8541 | `content/` (in `scripts/build_site.py`) |
| T7 | Executive summary | done | c39d8541 | `docs/summary.html` (generated) |
| T8 | Integration: build check, link check, PR to `main`, merge, Pages deploy | in progress | c39d8541 | `docs/`, `COORDINATION.md` |

## Log (append-only)

- **2026-11-14 (UTC)** — c39d8541 claimed T1–T8 on `arena/c39d8541-x1`. No other session has claimed any task. No merge conflicts occurred.
- **2026-11-14** — T1 complete. Repo at claim time: `README.md` (one line, `# X1`), no other files, one commit (`dab199c Initial commit`). See irregularities I-01 to I-04.
- **2026-11-14** — T2 complete. Data pulled from `https://www.nfl.com/standings/`, `https://www.nfl.com/schedules/2026/by-week/week-10`, and `https://www.nfl.com/injuries/` (all 8 chunks). Transcribed rows are checked against the source text; see Verification below.
- **2026-11-14** — T3 backtest run on the nflverse `nfldata` snapshot (commit `a04d58c0`). Result: **zero strategies pass the validation gates** because line provenance is unverified (gate G0). Details in `data/strategy_leaderboard.csv`.

## Verification performed (per task)

- **T2 standings:** 32 rows. Column meanings taken from the legend printed on the same NFL.com page (W, L, T, PCT, PF, PA, NET PTS, STRK). Consistency check: for every team, `PF − PA = NET PTS` and `W/(W+L+T)` matches PCT ±0.001 (run in `scripts/verify_data.py`).
- **T2 schedule:** 14 games + 4 bye teams = 32 clubs. Checked each game against the NFL.com schedule text and the game-level headers on the injury page (kickoff times and networks match in both places).
- **T2 injuries:** every row was copied from the official injury report text. Row counts per game are reconciled in `scripts/verify_data.py`. Each row links to the player's NFL.com page (from the report) and to the report itself. Rows with irregularities are listed in I-05 to I-08.

## Irregularities and items flagged for review

| ID | Area | Item | Source(s) | Status |
|----|------|------|-----------|--------|
| I-01 | Repo | `README.md` is a single line (`# X1`). No description, license, or usage notes. | `README.md` @ `dab199c` | flagged |
| I-02 | Repo | Only one commit on `main`. No history to check authorship or changes. | `git log` | flagged |
| I-03 | Repo | The project brief references `session-<id>/<task>` branches and a sub-section for each task. Arena branch policy forbids other branches for this session, so the brief's branch method was not followed (see Session and branch policy). | Project brief; Arena policy | flagged |
| I-04 | Repo | The brief contains HTML-escaped text (e.g. `&amp;amp;lt;id&amp;amp;gt;`, `[COORDINATION.md](http://COORDINATION.md)`). The intended values were read as `session-<id>/<task>` and `COORDINATION.md` in the repo root. | Project brief | flagged |
| I-05 | Injuries | Puka Nacua (LAR, WR) is listed as "Did Not Participate In Practice" with **no injury designation**. NFL.com news on the same site (retrieved 2026-11-14) reports an injury (turf toe, sprained MCL and PCL) and says he is likely to be placed on IR. The report does not reconcile with the news. | [NFL injury report](https://www.nfl.com/injuries/) · [NFL.com news: Nacua to IR](https://www.nfl.com/news/rams-wr-puka-nacua-likely-to-be-placed-on-injured-reserve-with-turf-toe-sprained-mcl-and-pcl) | flagged |
| I-06 | Injuries | Several players are listed "Did Not Participate In Practice" with no injury descriptor (e.g., Aaron Donald, Braden Fiske, Malik Hooker, Von Miller, Ladd McConkey, Trey Pipkins, Branson Taylor, Brenen Thompson, Isas Waxter, Kendall Williamson, Bud Dupree, Derick Hall, Byron Young, B.J. Hill, Dexter Lawrence, Ed Oliver, Christian Darrisaw, Jake Matthews-type cases). Reason for absence is not stated. | [NFL injury report](https://www.nfl.com/injuries/) | flagged |
| I-07 | Injuries | Internal inconsistency: a player is shown "Full Participation in Practice" but Game Status "Out" (e.g., BJ Green II, JAX, Forearm). Report conventions for this combination are not documented on the page. | [NFL injury report](https://www.nfl.com/injuries/) | flagged |
| I-08 | Injuries | Some player link slugs differ from the printed name (e.g., "Jacob Hummel" → `/players/jake-hummel/`; "Kam Curl" → `/players/kamren-curl/`; "Gervon Dexter Sr." → `/players/gervon-dexter/`). Likely a naming convention on NFL.com; the link is kept as published. | [NFL injury report](https://www.nfl.com/injuries/) | flagged |
| I-09 | Schedule | Munich game is listed on NFL.com as "Patriots at Lions" (NE listed first). A third-party page calls it "Patriots vs. Lions". The NFL.com listing is used. | [NFL Week 10 schedule](https://www.nfl.com/schedules/2026/by-week/week-10) | flagged (minor) |
| I-10 | Data | Line source (`spread_line`, `total_line`, moneylines) in the nflverse `nfldata` repo is **not documented** with a named provider. The data may come from a sportsbook or aggregator. Provenance cannot be confirmed from an official source. | [nfldata DATASETS.md](https://github.com/nflverse/nfldata/blob/master/DATASETS.md) | flagged — **blocks gate G0** |
| I-11 | Data | Game results and team/season tables in `nfldata` are compiled from third-party sources (not NFL.com). Spot-check of the 2026 Week 10 Thursday game matches NFL.com (see T3 checks). Full line-by-line match against NFL.com for 2006–2025 was **not** performed. | [nfldata](https://github.com/nflverse/nfldata) | flagged |
| I-12 | Data | No official depth-chart source collected yet. Starter vs backup status cannot be verified from official data at this time. | — | flagged (blocks T4) |
| I-13 | Data | No prop-bet odds source and no official player-stat source collected yet. Player-prop strategies cannot be tested. | — | flagged (blocks part of T3) |

## Pages

- Site: `docs/` on `main`, served by GitHub Pages (configured in Step T8; URL recorded below after deploy).
- PR and merge record: filled in at T8 completion.
