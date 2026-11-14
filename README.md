# Fourth Down — NFL Strategy Lab

A static, evidence-first research dashboard and requirements register for NFL line origination and strategy evaluation. This is a research specification—not a betting product, live data service, or source of picks.

## Pages

- `index.html` — executive summary and navigation
- `research.html` — candidate signal families, line workflow, and correlation methodology
- `validation.html` — staged gates and leaderboard competition design
- `availability.html` — injury/depth tracking schema for offense and defense
- `sources.html` — official NFL and NIST source register, verification scope, and limitations
- `questions.html` — decision questions, knowns, gaps, and discovery suggestions
- `review.html` — irregularities, unverified values, and review queue

## Evidence policy

The repository began without an application, NFL data, odds history, tests, or deployment workflow. No NFL live values, injury statuses, odds, correlations, picks, or measured strategy performance are invented. Each proposed method is labeled as untested; empty values are left blank. Primary NFL links are provided beside relevant methodology, and limitations are explicit. A source page link does not mean its changing contents have been captured or independently verified for a specific event.

Sources linked in the site include NFL.com injury reports, statistics, schedules, and team pages; NFL Football Operations and Next Gen Stats material; and NIST reference material for statistical definitions and uncertainty. Review `sources.html` for the source register and `review.html` for all limitations. See `COORDINATION.md` for scope and verification history.

## Local preview

Open `index.html` in a browser or serve this directory with any static HTTP server. All pages are plain HTML/CSS and need no build step.

## GitHub Pages

GitHub Pages is deployed at [karagemop466-tech.github.io/X1](https://karagemop466-tech.github.io/X1/). The deployment was recorded in the coordination log; a workflow runs on pushes to `main`. A lightweight static checker now verifies local links and that each research-table row links to an official source host before deployment.
