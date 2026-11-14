<<<<<<< HEAD
# X1 — Fourth Down: NFL Line Lab

Verified NFL data, a line-origination methodology, and a skill-based strategy leaderboard —
built so that **nothing is published without an official source**, and anything unprovable is
left visibly blank and flagged.

**Live site:** https://karagemop466-tech.github.io/X1/

## What is in here

| Path | Contents |
|---|---|
| `index.html`, `pages/` | The published dashboard (generated — do not hand-edit) |
| `assets/site.css` | Styling (hand-edited) |
| `data/nfl/*.tsv` | Transcribed official tables, one source link per row |
| `data/*.json` | Machine-readable registers: questions, flags, suggestions, gates, signals, strategies |
| `docs/EXECUTIVE-SUMMARY.md` | The summary in plain markdown |
| `docs/methodology/` | Line origination, correlation, validation gates, leaderboard, availability |
| `docs/sources/sources.md` | Source registry and the verification tiers |
| `docs/review/repo-review.md` | Line-by-line review of the repository and its own defects |
| `tools/` | Data build, integrity checks, site generator, link checker |
| `COORDINATION.md` | Shared task board for parallel agent sessions |

## The rule this repository is built around

> If a value cannot be confirmed from an official source, the cell stays blank and the item is flagged.
> Nothing is inferred, and no number is invented to fill a table.

Consequences you will see on the site: **no prices, no correlation values, no strategy results**.
Those require a licensed odds feed, licensed snap counts and a scored window, none of which exist here yet.

## Reproduce every check

```bash
python3 tools/build_availability.py   # rebuild the derived availability table
python3 tools/verify_data.py          # 2,944 integrity assertions over every published table
python3 tools/build_site.py           # regenerate index.html and pages/
python3 tools/check_links.py          # resolve internal links, allow-list external hosts
```

All four must pass before anything is published; CI (`.github/workflows/verify.yml`) enforces it.

## Data snapshot

Everything is a snapshot dated **2026-11-14** — 2026 NFL season, Week 10.
The injury report changes daily, so treat the tables as dated evidence, not a live feed.

## Corrections

Corrections are published, not silently applied. The current list is on the site's
**Flagged for review** page and in `docs/review/repo-review.md` (defects D-01 to D-03).
=======
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
>>>>>>> origin/main


---

## Appendix — previous README from `main` (preserved)

The dashboard text below was on `main` before the integrated release. It described the
design-specification site built by `arena/6f377170-x1` and `arena/226be516-x1`; those pages are
preserved in git history (`16ac19e`, `770ae96`). It is kept here so nothing from that session is lost.

<<<PRESERVED VERBATIM>>>

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
