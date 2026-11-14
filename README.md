# Fourth Down — NFL decision support

An evidence-first NFL research workspace, published as a static GitHub Pages
site. Every published row links to the official NFL document it came from;
anything that cannot be read from an official source is left blank and listed
on the **Flagged for review** page.

**Live site:** https://karagemop466-tech.github.io/X1/

## What this is

The project collects official NFL data on a schedule, derives two analytical
datasets from it, and renders a dashboard that a reviewer can check row by row
against the league's own publications.

| Area | What is published |
|---|---|
| Requirements | Every requirement with its status and the artefact that satisfies it |
| Questions & gaps | What is known, answered, missing, and the action that closes each gap |
| Strategies | 13 candidate strategies across single bets, parlays and player-prop combinations |
| Validation gates | 10 pre-registered criteria a strategy must clear before it can be ranked |
| Correlations | Measured dependence with sample sizes and confidence intervals, plus what cannot be measured |
| Schedule | The official weekly schedule with the date, result and venue for every published game book |
| Injuries & depth | The official injury report joined to the replacement who must take the slot |
| Suggestions | Proposals for review and selection before any of them are implemented |
| Flagged for review | Everything that could not be verified from an official source |
| Sources | Every official endpoint read, and what each one authoritatively provides |

## The evidence rule

Nothing on this site is inferred, estimated or carried over from a secondary
source. Specifically:

* every populated table row carries an HTTPS link to an official NFL endpoint;
* a value that cannot be read from that source is rendered **blank**, not
  guessed;
* anything unverifiable appears on the **Flagged for review** page with a
  manual-review link;
* the verifier parses the **rendered HTML**, not the generator's intent, so a
  rendering bug cannot slip past it.

The one document hosted off an NFL domain is the published NFL Media Access
Policy, which the Pro Football Writers Association hosts. It is labelled as
such in the publisher column of the Sources page.

## How it works

```
official NFL endpoints
        │
        ▼
  nflx.collect     parsers for the injury report, standings, schedule and
                   player statistics
  nflx.gamebook    parser for the official Game Book PDF: lineups,
                   substitutions, inactives, officials, weather, box score,
                   team statistics and playtime
        │
        ▼
  nflx.depth       unavailable starter → the replacement who takes the slot
  nflx.correlation measured dependence with Fisher-z confidence intervals
        │
        ▼
  nflx.build_site  renders every page
  nflx.verify      fails the build if any rule above is broken
```

The collector, the analysis and the renderer are pure standard-library Python,
so the pipeline runs on a GitHub Actions runner with no install step beyond
`pypdf` and `numpy`.

### Why the collection runs in CI

The agent sandbox cannot reach NFL hosts, but GitHub Actions runners can. The
refresh workflow therefore does the retrieval, and commits both the data and
a log of the run back to the branch so a run can be inspected without access
to the Actions log store.

## Running it locally

```bash
python -m pip install pypdf numpy
PYTHONPATH=src python -m nflx.pipeline --out data/nfl --cache .cache/nflx
PYTHONPATH=src python -m nflx.build_site --data data/nfl --out _site
PYTHONPATH=src python -m nflx.verify --site _site
```

## The verifier

`nflx.verify` is the gate that stops a broken site being published. It checks
the rendered HTML for:

1. every populated table row links to an official source;
2. every external link uses an allowed official host;
3. every internal link resolves;
4. no placeholder content;
5. every page is reachable from the landing page;
6. no page is orphaned.

A failure exits non-zero and the workflow does not publish.

## What is deliberately not claimed

No strategy is reported as having an edge, and the leaderboard is published in
that state rather than with invented numbers. Closing-line value — the gate
that decides whether a strategy beats the market — cannot be tested without a
licensed, timestamped price history, and the league publishes no such series.
The strategies are specified and gated; the outcome is reported as unknown.

## Layout

```
src/nflx/         the pipeline
  sources.py      the registry of official endpoints
  http.py         dependency-free HTTP client with a disk cache
  htmlparse.py    HTML table extraction
  collect.py      parsers for the official endpoints
  gamebook.py     the official Game Book PDF parser
  gamebook_stats.py  team statistics, playtime and the penalty log
  depth.py        depth-chart deficiency analysis
  correlation.py  correlation and joint probability
  strategies.py   the strategy catalogue, gates and leaderboard
  aliases.py      player identity resolution across naming conventions
  analysis.py     the derived datasets
  build.py        shared page furniture
  pages.py        the page renderers
  build_site.py   the build entry point
  verify.py       the strict verifier
data/nfl/         the collected datasets, with a provenance manifest
.github/workflows/refresh-data.yml   collect → build → verify → publish
```

## Coordination

Parallel sessions coordinate through `COORDINATION.md`, which records the
claim protocol, the file scope each session owns and the log of what has been
done. Shared outputs — the site index, the navigation and the published
dataset directory — are changed only during final integration.

## Licence and attribution

All data belongs to the National Football League and is used here by reference
to the league's own publications. The Game Book is published by the NFL for
the express purpose of assisting media coverage; it is not redistributed here.
