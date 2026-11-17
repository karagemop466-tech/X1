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

## Added 2026-11-17 — session `arena-9d8c298c-x1` (the R1 round)

Three pages, three builders, one pre-registration. All of them read files, none of them touch
the network, and none of them writes outside `data/lab/reads/**`, `data/lab/escrow/**` and
`tools/lab/**`.

| Page | Builder | What it publishes |
|---|---|---|
| `lab/reads.html` | `tools/lab/build_reads.py` | the 2026-11-17 official read: 14 Week 10 finals, the 13-fixture Week 11 slate, the standings, venue evidence and the injury spot-check, with the ten checks that gate them re-run from the files |
| `lab/escrow.html` | `tools/lab/build_escrow.py` | PR-04: 52 pre-kickoff forecast rows (side, both total estimators, moneyline), the settlement ledger, the luck panel, and the PR-01-vs-PR-04 delta on the same 13 fixtures |
| `lab/closure.html` | `tools/lab/build_closure_measurement.py` | what still blocks Week 10 in `data/results`, counted by the feed's own gates, with the three ways out and their cost — measured, not fixed |

The reads pack is transcribed from live official pages and the fetch tool returns parsed text, so
`data/lab/reads/2026-11-17/manifest.json` hashes the *transcriptions*, not HTTP bytes, and says so.

Reproduce any of it:

```bash
python3 tools/lab/build_reads.py --check                # the pack's ten checks, from the files
python3 tools/lab/build_escrow.py --check               # pre-kickoff ordering + immutability guard
python3 tools/lab/build_closure_measurement.py --check  # the closure numbers, from the committed builder
python3 tools/lab/build_site.py                         # rebuild the pages, then --check the tree
```

Two limits of this round are worth stating before anyone reads a number off those pages. The price
columns are blank on every escrow row, because no source with a book and a timestamp exists here —
so there is no residual, no CLV and no ROI, and there will not be one until Q-02 is decided. And the
settled ledger has `n = 1`: the mechanism for scoring a forecast against an official final works, and
it has nothing to say.
