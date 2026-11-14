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

## Snapshot annex (session `arena-a78e0158-x1`)

A parallel, independently built **quantitative annex** is integrated alongside the canonical
site above. Where the canonical site deliberately publishes no numbers, the annex publishes
**computed** values with full inputs, code and audit trail:

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

Cross-check note: both independent transcriptions agree — standings 32/32 identical
(`data/standings_2026.csv` ↔ `data/nfl/teams_standings_2026_w10.csv`).
