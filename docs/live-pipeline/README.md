# Live pipeline (session `arena-d577959f-x1`)

The auto-refreshing half of the X1 site. Everything in `live/` and `data/pipeline/`
is produced by this pipeline; everything else on the site belongs to the other
sessions and is untouched by it.

```bash
python3 -m pipeline                       # collect + verify + write data/pipeline/*.json
python3 scripts/pipeline/verify_data.py   # row-level source coverage
python3 scripts/pipeline/verify_site.py   # links + datasets for live/
```

## Layout

| Path | What it is |
|---|---|
| `pipeline/` | Collectors. Python standard library only — no API keys, no dependencies. |
| `data/pipeline/` | 15 datasets. Every row carries the official URL it was read from. |
| `live/` | 15 dashboard pages; every table is rendered from the JSON above. |
| `assets/x1-live/` | Dashboard CSS and the shared table renderer. |
| `scripts/pipeline/` | Verifiers for this section. |
| `.github/workflows/data-refresh.yml` | Schedule: every 6 hours, plus game days. |

## The verification rule

1. Every row links to the official page its values came from.
2. A value the official source does not publish is stored as `null`, rendered as an
   em dash, and flagged — never estimated.
3. Hosts are allow-listed: nfl.com, or a club domain the league itself lists at
   <https://www.nfl.com/teams/>.
4. An empty pull never overwrites good data.

## What is deliberately blank

Betting prices and game results have no official public source, so the market-lines
table ships empty and the leaderboard result columns stay blank. Gates that depend on
outcomes are defined but left unenforced rather than given an invented threshold.

See `methodology.md` for the statistics, and `project-brief.md` for the verbatim brief
that `requirements`, `questions` and `suggestions` quote row by row.
