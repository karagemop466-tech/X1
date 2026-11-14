# Sources register — line desk, session `arena/56769365-x1`

Every URL below was fetched (or attempted) from the sandbox that built `lab/`, on
2026-11-14. A source is listed with what it actually provided, not what it is expected to
provide. Hosts marked **blocked** returned no data and are listed so a reviewer can see the
shape of the evidence rather than only its successes.

## Reachable, and used

| Source | URL | What it provided | How it is pinned |
|---|---|---|---|
| nflverse `nfldata` repository archive | https://codeload.github.com/nflverse/nfldata/tar.gz/refs/heads/master | `data/games.csv`, `initial_lines.csv`, `closing_lines.csv`, `sc_lines.csv` | SHA-256 of the archive **and** of each extracted file, in `data/lab/upstream/_pin.json` |
| nflverse `nfldata` column definitions | https://github.com/nflverse/nfldata/blob/master/DATASETS.md | the publisher's own definition of `spread_line`, `total_line`, `result`, `total`, `location` | line numbers cited per field in `tools/lab/common.py` |
| `games.csv` (raw file view) | https://github.com/nflverse/nfldata/blob/master/data/games.csv | per-row source link printed on the site | per-row link |
| `closing_lines.csv` (raw file view) | https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv | per-row source link for closing numbers | per-row link |
| `initial_lines.csv` (raw file view) | https://github.com/nflverse/nfldata/blob/master/data/initial_lines.csv | per-row source link for the 2021 initial lines | per-row link |
| GitHub REST API | https://api.github.com/repos/nflverse/nflverse-data/releases | listed 25 releases and their assets — used to establish that **no** odds/line release exists | response summarised in this file |
| GitHub REST API (tree) | https://api.github.com/repos/nflverse/nflverse-data/git/trees/main?recursive=1 | 34 files; no line/odds data anywhere in the package | response summarised here |

## Reachable but **not** authoritative for a price

| Source | URL | Why it is not used as the price benchmark |
|---|---|---|
| nflverse `games.csv` line columns | https://github.com/nflverse/nfldata/blob/master/DATASETS.md#L109 | the publisher names no book and does not say whether the number is opening or closing |
| nflverse `initial_lines.csv` | https://github.com/nflverse/nfldata/blob/master/data/initial_lines.csv | covers 2021 only; its numbers are inconsistent with `games.csv` for 510 of 544 spreads |
| nflverse `closing_lines.csv` | https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv | covers 2006–2018 only; no book, no timestamp, price on 43.2% of rows |

## Blocked from this environment (measured, not assumed)

| Host / URL | Attempt | Result |
|---|---|---|
| https://www.nfl.com/standings/ | `curl -o /dev/null -w %{http_code}` | `000` — no connection |
| https://www.nfl.com/injuries/ | same | `000` |
| https://raw.githubusercontent.com/nflverse/nfldata/master/README.md | same | `000` |
| https://github.com/nflverse/nflverse-data/releases/download/player_stats/player_stats.csv | `curl -L` | `302` to `release-assets.githubusercontent.com`, **0 bytes** |
| https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_2026.csv | `curl -L` | `302`, **0 bytes** |
| `playwright` browser download (for a render test) | `playwright install chromium-headless` | download failure (`code=1`) |

Consequences, all published on the site:

* no league page could be re-fetched, so **no existing nfl.com row was re-verified by this
  session** — the injury and standings tables are carried from earlier sessions and are
  labelled as such;
* no nflverse *release* dataset (player stats, injuries, depth charts, pbp, snap counts) could
  be used, which is why there are no prop markets and no multi-season injury history;
* the repository archive was the only nflverse source that could be read, which is why the
  line desk is built on it.

## Carried from earlier sessions (not re-fetched here)

| Data | Where it lives | Original source | Status in this session |
|---|---|---|---|
| Week 10 injury report, 345 rows | `data/pipeline/injuries.json` | https://www.nfl.com/injuries/ (collected by `arena/d577959f-x1`) | read, joined, **not re-fetched** — the host is blocked |
| Club depth charts, 1,813 rows, 31 clubs | `data/pipeline/depth_charts.json` | each club's own depth-chart page | read; per-row club link printed |
| Week 10 schedule and standings | `data/pipeline/*.json` | https://www.nfl.com/ | not used by this round's builders except for context |

## Verification tiers used on `lab/`

| Tier | Meaning | Where it applies |
|---|---|---|
| **A — official** | a league or club page, fetched and cited | club depth charts, injury report (both carried, both linked) |
| **B — published third party, pinned** | a named dataset, byte-hashed, with the publisher's own field definitions | everything from nflverse `nfldata` |
| **C — derived** | computed by a script in this repository, reproducible from A or B | fair lines, strategy results, correlations |
| **D — unsourced** | **not published**; emitted as `null` and flagged | prop markets, opening prices, book identity, timestamps, injury effect |

A price row is tier B, not tier A. That is the single most important sentence in this
document: **no official source publishes a betting price**, and the line desk does not pretend
otherwise.
