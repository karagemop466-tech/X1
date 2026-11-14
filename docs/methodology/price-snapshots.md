# Price-snapshot store

**Requirement:** "Add a price-snapshot store that records opening and closing numbers for
every market we originate." *(Owner's brief, T10, session `arena-52aabfa8-x1`.)*

**Machine-readable outputs:** `data/prices/price_snapshots.csv` (20,088 rows, 2,232 games,
seasons 2019–2026) and `data/prices/price_store_meta.json` (sources, conventions, flag
expansions, checks).
**Builder:** `python3 tools/build_price_store.py` — deterministic, offline, exits non-zero
if any check fails.

---

## 1. Shape of the store

Nine rows per game — three markets × both snapshots, with the moneyline split by side:

| market | side | opening row | closing row |
|---|---|---|---|
| `SPREAD` | *(blank — signed game line)* | one row **per team** (the source publishes per-side) | one row (signed game line) |
| `TOTAL` | *(blank)* | one row (Over/Under verified identical) | one row |
| `MONEYLINE` | `AWAY` / `HOME` | one row each | one row each |

Every row carries `snapshot` ∈ {`opening`, `closing`}, the `line` exactly as its source
publishes it, a `source_key` resolving to the URL registry in the meta file, the source's
own `convention`, and a `flags` code when the value does not exist.

## 2. What is filled and what is blank

| Cells | Count | Why |
|---|---|---|
| closing values present | 8,492 | `games.csv` carries spread/total/moneyline for 2,123 of 2,232 games (2019–2026; 2026 posted through week 11) |
| closing cells blank | 436 | flag `NO-CLOSING-LINE-IN-MIRROR` — 109 future 2026 games with no posted line |
| opening values present | 816 | `initial_lines.csv` covers **2021 regular season only**, spread + total only: 272 games × (2 spread sides + 1 total) |
| opening cells blank | 10,344 | `NO-OPENING-DATA-SEASON` (all other seasons) and `NO-OPENING-MONEYLINE` (no source anywhere publishes opening moneylines) |

**Blank means the source does not publish it.** No cell is inferred, averaged or carried
forward. Every value that *is* present is a third-party benchmark: no official NFL or club
source publishes betting prices (flag **F-06**, question **Q-02**), so no row in this store
is league-verified, and the meta file says so on the `official` source entry.

## 3. Conventions are kept verbatim, not merged

- **Closing spread** is a single signed game line: *positive = home team favoured*
  (nflverse `DATASETS.md`). The legacy column names in
  `data/lines/originated_lines_2026_week10.csv` say `…_away`; the number itself is
  identical under the home-margin and away-handicap readings, so the name is a cosmetic
  misnomer, not a data error (recorded as a grey note for reviewers).
- **Opening spread** is published *per team* ("TB −6.5"), negative = that team favoured.
- The two conventions are therefore **not directly comparable without a normalisation
  step**, which this store deliberately does not perform (normalising would be an
  inference about intent). That step — and the CLV studies it unlocks — is listed as a
  follow-up limitation in the meta file, tied to Q-02.

## 4. Checks (all must pass or the builder exits 1)

| ID | Check | Result |
|---|---|---|
| P1 | every present line parses as a number (9,308 values) | pass |
| P2 | 2021 opening spread pairs are exact negatives | pass, 272/272 |
| P3 | 2021 opening Over == Under | pass, 272/272 |
| P4 | all 14 Week 10 2026 games carry complete closing spread/total/ML | pass, 14/14 |
| P5 | the store's game set is identical to the verified results feed's | pass, 2,232 games |
| P6 | exactly 9 rows per game, no duplicate market/side/snapshot slot | pass, 20,088 rows |

## 5. How this differs from the existing `market_lines.json`

`data/market_lines.json` (the pipeline's market table) ships **empty on purpose** because
no *official* price source exists, and the verification rule forbids filling it. This store
solves a different problem: it records what the *reachable third-party* sources publish —
opening and closing, per market, per game — with the tier stamped on every row, so the
benchmark used by backtests is citable and the gaps are enumerable instead of invisible.
The two files never mix tiers: `market_lines.json` stays empty until an official or
owner-supplied feed exists (Q-02).
