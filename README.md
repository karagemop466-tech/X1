# X1 — NFL Decision & Signal Dashboard

An autonomous system that **collects, organizes, and analyzes NFL data** to **originate our own
betting lines**. Strategies (single bet, parlay, player-prop combos) compete on a **leaderboard** and
must pass **validation gates** that remove luck and isolate skill. Injury and depth-deficiency
tracking (starters replaced by 2nd/3rd/4th-string backups, on offense and defense) is a core edge
signal.

## What's in this repo

A **live GitHub Pages site** (dashboard-style) plus the coordination/verification backbone.

- `index.html` — landing / dashboard
- Subpages organized by category:
  - `executive-summary.html` — executive summary
  - `requirements.html` — full list of requirements
  - `questions.html` — open questions & information gaps
  - `suggestions.html` — dedicated, reviewable suggestions board
  - `strategies.html` — line-generation strategies (single / parlay / props)
  - `validation-gates.html` — the 7-gate validation pipeline
  - `correlations.html` — correlation methodology & values
  - `injuries.html` — injury tracking & depth deficiency
  - `leaderboard.html` — strategy competition
  - `data-standings.html` — verified 2026 standings (all 32 teams)
  - `data-lines.html` — verified Week 10 market lines
  - `sources.html` — official source index
  - `flagged-for-review.html` — unverified / caveated items
- `assets/` — shared CSS/JS
- `data/` — machine-readable verified exports (`standings-2026.json`, `flagged-count.json`)
- `scripts/verify_links.py` — internal broken-link checker run before deploy
- `COORDINATION.md` — shared task board, verification log, and deploy record

## Verification policy

Every numeric table row carries a link to an **official source**. NFL league data (standings, injuries,
depth) is sourced only from **NFL.com**. Market lines are sourced from authoritative sportsbook/aggregator
sources and flagged as a market (not league-official) source type. Any value that cannot be confirmed
from an official source is left **blank** and listed on the **Flagged for Review** page — nothing is
inferred or filled in, and nothing is published without a source.

## Live site

Published via GitHub Pages: **https://karagemop466-tech.github.io/X1/**

## Automation

The pipeline (fetch → verify → organize → analyze → validate → publish) is designed to run without
manual input. `scripts/verify_links.py` enforces the no-broken-links build requirement before publish.
