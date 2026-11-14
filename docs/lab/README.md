# `docs/lab` — how the line desk is built, and what each number means

Session `arena/56769365-x1`. Every page under `lab/` is generated from `data/lab/*` by
`tools/lab/build_site.py`. Nothing in `lab/` is hand-written, and no number on a page is typed
in by hand: each one comes from a JSON artefact that carries its own provenance block.

## The artefacts, in dependency order

| Step | Script | Writes | Depends on |
|---|---|---|---|
| 1 | `tools/lab/fetch_upstream.py` | `data/lab/upstream/*` + `_pin.json` | the network, once |
| 2 | `tools/lab/build_prices.py` | `data/lab/prices/*` | upstream |
| 3 | `tools/lab/build_results.py` | `data/lab/results/*` | upstream |
| 4 | `tools/lab/build_lines.py` | `data/lab/lines/*` | results |
| 5 | `tools/lab/build_strategies.py` | `data/lab/leaderboard.json` | lines |
| 6 | `tools/lab/build_correlation.py` | `data/lab/correlations.json` | results, lines |
| 7 | `tools/lab/build_deficiency.py` | `data/lab/deficiency.json` | `data/pipeline/*` (earlier session) |
| 8 | `tools/lab/build_questions.py` | `data/lab/questions.json`, `suggestions.json` | 2–7 |
| 9 | `tools/lab/build_summary.py` | `data/lab/summary.json` | 2–8 |
| 10 | `tools/lab/build_site.py` | `lab/*.html` | 2–9 |

`python3 tools/lab/build_all.py` runs 1–10 and stops at the first failure, so a page cannot
show numbers from a step that did not finish.

## The rule every artefact follows

1. **A value is published only if the source prints it.** A missing field is `null` in the
   JSON, an em dash on the page, and a counted line in the artefact's `coverage` block.
2. **Every cell names its source.** At column level that is the file, the column and the
   definition URL; at run level it is the SHA-256 of the exact bytes read.
3. **Derived values say they are derived.** The fair line is derived; the market line is
   sourced; the page keeps them in separate columns and labels the difference.
4. **A claim has to be recomputed on every build.** Coverage figures, defect measures and
   self-checks are functions of the data, not constants in the prose. If they disagree with
   the data, the build fails or the prose changes.

## What each number means (the short version)

| Term | Meaning here |
|---|---|
| **fair side** | our originated spread, home convention (negative = home favoured), derived |
| **market side** | the publisher's spread converted to the same convention |
| **side diff** | fair minus market, in points; negative means we make the home team stronger |
| **n** | paired observations actually used, never the rows available |
| **break-even bar** | the probability a *ticket* must win at: 52.38% at −110, 27.44% for a two-leg −110 parlay, per-ticket for a moneyline |
| **z** | Poisson-binomial test against the sum of per-ticket bars, not against 52.38% |
| **signal positive** | z ≥ 1.96 with a bootstrap interval above the bar |
| **demotion** | any of D-01…D-04 fires; the strategy returns to paper |

## The three things this round refuses to do

1. **Price a market with no book.** Every closing line row is labelled as an unnamed
   composite, because the source names no book.
2. **Call a file-name "opening" number an opening number.** `initial_lines.csv` covers 2021;
   the closing file covers 2006–2018. They do not overlap, so no market in this store has
   both, and the page says so instead of pairing them anyway.
3. **Claim an injury effect on the line.** Depth is measured; effect is not, and the difference
   is published on the Deficiency page and in Q-M2.

## Reproducing a single number

Every artefact's `_files` block carries the SHA-256 of the input it was built from. To check
one published figure:

```bash
python3 tools/lab/fetch_upstream.py            # re-vendor, then compare _pin.json hashes
python3 tools/lab/build_prices.py              # prints the coverage summary it wrote
python3 -c "import json;print(json.load(open('data/lab/prices/price_coverage.json'))['totals'])"
```

If the hashes differ from the committed `_pin.json`, the upstream moved and the numbers are a
*different snapshot* rather than wrong; the pin file is what makes that distinction possible.
