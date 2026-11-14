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
