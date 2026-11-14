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

---

## The research lab (`research/`)

A second, independent implementation lives in this repository and is published alongside the
dashboard at **`/research/`**. It answers the question the dashboard deliberately leaves open:
*what do the strategies actually do once you price them and test them out of sample?*

| Path | Contents |
|---|---|
| `research/` | The research site: model lines, strategies, leaderboard, gates, correlations, luck analysis, player props, injuries and depth (generated - do not hand-edit) |
| `src/x1/` | The Python package: `config`, `sources`, `ingest`, `prep`, `model`, `strategies`, `evaluation`, `gates`, `correlation`, `leaderboard`, `props`, `injuries`, `content` |
| `scripts/run_pipeline.py` | Downloads the inputs, fits the model, evaluates the library, applies the gates and writes the processed tables |
| `scripts/build_research_site.py` | Regenerates `research/` from `data/site/payload.json` |
| `data/processed/` | The tables that back every published number in the research site |
| `data/raw_manifest.json` | Provenance for every input file: repository, path, bytes, SHA-256 |
| `data/raw/official_injuries_w10_2026.csv` | A hand transcription of the official Week 10 injury report (the only raw file that cannot be re-downloaded) |

```bash
pip install -r requirements.txt
python3 scripts/run_pipeline.py      # ingest -> model -> strategies -> gates -> payload
python3 scripts/build_research_site.py   # regenerate research/
```

### The validation protocol

A strategy earns reward **only** by passing all eight gates:

| Gate | Name | Threshold |
|---|---|---|
| G1 | Sample sufficiency | >= 100 settled out-of-sample bets |
| G2 | Out-of-sample integrity | Parameters chosen only from earlier seasons; no duplicate bets |
| G3 | Statistical significance | Bootstrap 95% CI lower bound > 0 **and** sign-flip permutation p <= 0.05 |
| G4 | Economic significance | ROI >= 2% per unit staked |
| G5 | Beats naive baselines | ROI above every always-on baseline on the same window |
| G6 | Luck robustness | Positive ROI after removing one-score games and blowouts |
| G7 | Parameter stability | >= 60% of neighbouring parameter values stay positive |
| G8 | Non-redundancy | Correlation with an accepted strategy <= 0.85 |

Reward: `1000 * ROI * min(1, bets / 300) * confidence`, where *confidence* is the share of the
bootstrap interval that stays above zero. A strategy that fails any gate earns zero.

### What the research lab adds to the dashboard

- **A priced, provenance-documented benchmark.** The dashboard withholds prices and correlations
  because the line provenance was unverified. The research lab names the benchmark explicitly (a
  third-party closing line carried in the `nflverse/nfldata` mirror, fingerprinted in
  `data/raw_manifest.json`) and states it on every page that uses it.
- **Originated lines.** A walk-forward Poisson points model produces its own spread and total for
  7,154 games, fitted only on earlier seasons, and is compared with the market benchmark so the
  size of the opportunity is published rather than assumed.
- **Measured strategy results.** Sixteen pre-registered strategies, evaluated out of sample from
  2015 to 2026 with parameters re-selected each season. One passes every gate.
- **Correlation values, luck removal and player-prop mathematics**, with the parlay break-even
  arithmetic that shows when a two-leg combination is impossible at -110 legs.

### The rule both halves follow

> If a value cannot be confirmed from a cited source, the cell stays blank and the item is flagged.
> Nothing is inferred, and no number is invented to fill a table.

The research lab adds one honest extension: where the value is confirmable but the *source is a
community mirror rather than the league*, the row is published **with the mirror named and linked**,
and the item is repeated on the Flagged for Review page. It is never presented as league-verified.

---

## Appendix - preserved README from the first session on `main`

The text below was on `main` before the integration and is preserved verbatim.

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
>>>PRESERVED VERBATIM>>>

---

## Snapshot annex (session `arena-a78e0158-x1`)

A parallel, independently built **quantitative annex** is integrated alongside the sites above.
Where the canonical site deliberately publishes no numbers, the annex publishes **computed**
values with full inputs, code and audit trail:

| Path | Contents |
|---|---|
| `site/` | The X1 snapshot dashboard (10 pages; every row source-linked; CSVs mirrored under `site/data/`) |
| `data/nfl/`, `data/injuries/` | Verified snapshot: standings (cross-verified NFL.com ↔ nflverse, 32/32 exact), Week 10 schedule + byes, 9 international games, official 345-row injury report, QB map with conflicts flagged |
| `data/lines/` | Originated X1 lines, leak-free backtest (1,779 games), threshold sweep, computed correlation report with 95% CIs, team ratings |
| `data/strategies/` | Strategy registry with validation gates, leaderboard, luck-reference arithmetic, bet-log template |
| `data/raw/nflverse/` | nflverse/nfldata source copies + provenance README |
| `docs/annex/`, `docs/analysis/` | Annex review/sources/methodology docs; executive summary; decision matrix (Q1–Q12); suggestions register (SG-01..SG-13) |
| `code/` | Deterministic stdlib builders: `build_reference_data.py`, `build_lines.py`, `leaderboard.py`, `build_site.py` |

Headline (computed, not assumed): the v1 results-only model has **no betting edge** (ROI −6.1%…−2.6%
across thresholds) — registered `failed-gate` on the annex leaderboard; same-game spread/total
correlation φ = −0.023 (n=1,496); cross-game independence r = 0.001 (n=12,585); a true 55% capper
needs 991 bets for 95% confidence — the gates encode this so luck cannot be rewarded.

Rebuild the annex:

```bash
python3 code/build_reference_data.py   # verified CSVs from transcribed official data
python3 code/build_lines.py            # ratings, leak-free backtest, Week 10 lines, correlations
python3 code/leaderboard.py            # grades bets, scores strategies, checks gates
python3 code/build_site.py             # regenerates site/ (annex)
python3 scripts/verify_site_annex.py   # annex link + source-row check
```

Cross-check note: the independent standings transcriptions agree 32/32 exactly
(`data/standings_2026.csv` ↔ `data/nfl/teams_standings_2026_w10.csv`).

## Analytics lab (computed layer, session `arena/61ce8500-x1`)

`dashboard/lab-*.html` + `data/processed/` are generated by `scripts/build_data.py` (analytics,
correlations, Elo model lines, deficiency flags) and `scripts/build_lab_site.py` (lab pages): the
491-row Week 10 injury report with per-row ESPN source links, all-272-game 2026 schedule with
ATS/total results, computed 1999–2026 baselines, weekly-independence and spread↔total correlation
values, and a validation-gates worked example (look-ahead bias erased a fake backup-QB edge).
Regenerate with `python3 scripts/build_data.py && python3 scripts/build_lab_site.py`. Coverage
corrections merged into `data/raw/nflverse/README.md`: closing lines 2006–2018, opening lines 2021
only, win totals 2003–2020 — the 1999–2026 span lives in `games.csv` per-game line columns.
