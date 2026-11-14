# X1

NFL decision system: official-source data collection, injury and lineup-deficiency
tracking, originated lines, and a gated strategy leaderboard — published as a static
dashboard on GitHub Pages.

**Live site:** <https://karagemop466-tech.github.io/X1/> (published from `main`)

## What is in here

| Path | What it is |
|---|---|
| `/` (repo root) | The published dashboard. Plain HTML, CSS and vanilla JS; every table is rendered from JSON in `data/`. GitHub Pages serves the branch root. |
| `data/` | Every dataset, one file per table. Every row carries the official URL it was read from. |
| `pipeline/` | The collectors. Standard library only — no API keys, no dependencies. |
| `scripts/` | Verifiers: `verify_data.py` (row-level source coverage) and `verify_site.py` (links, data files, page integrity). |
| `docs/` | The project brief (verbatim) and methodology. |
| `assets/` | Dashboard CSS and the shared table renderer. |
| `COORDINATION.md` | Shared task board for parallel sessions. |
| `docs/` | `project-brief.md` (verbatim brief) and `methodology.md`. |

## How it runs without manual input

`.github/workflows/data-refresh.yml` runs on a schedule (every six hours, plus an extra
pass on game days) and on every push that touches the pipeline:

1. pull every dataset from its official source;
2. verify every row has an official source and no undeclared blank values;
3. commit the data, refusing to overwrite good data with an empty pull;
4. run the site verifier over the branch root, which is what Pages serves.

Pages is configured with the legacy branch builder on `/`, so every commit to
`main` rebuilds the live site automatically.

Run it by hand from the Actions tab, or locally with:

```bash
python3 -m pipeline          # collect + verify + write data/*.json
python3 scripts/verify_data.py
python3 scripts/verify_site.py
```

## The verification rule

1. Every row links to the official page its values came from.
2. A value the official source does not publish is stored as `null` and rendered as an
   em dash — never estimated, never recalled.
3. A row with a blank value or an integrity flag is marked `flag` and appears on the
   **Flagged for Review** page.
4. Hosts are allow-listed: a row may only cite nfl.com or a club domain the league
   itself lists on <https://www.nfl.com/teams/>.

## Sources

- <https://www.nfl.com/standings/league/2026/REG> — standings
- <https://www.nfl.com/injuries/> — official injury report
- <https://www.nfl.com/stats/team-stats/> — official team stats (offense and defense)
- <https://www.nfl.com/teams/> — the authoritative list of official club websites
- Each club's own official site — depth charts

Betting prices and game results have **no** official public source. Those tables ship
empty and flagged rather than filled in from somewhere else.
