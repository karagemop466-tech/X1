# Price-snapshot store (T15)

**Session `arena-1d3600f8-x1` · 2026-11-14**

## What the owner asked for

> Add a price-snapshot store that records opening and closing numbers for every market we originate.

## What exists

| Artifact | Purpose |
|---|---|
| `data/price_snapshots/snapshots.csv` | Append-only capture log. One row per price observation: `capture_type` ∈ opening / closing / intraday, with book, source URL, source type, verification status, timestamp. |
| `data/price_snapshots/market_index.csv` | One row per **originated market** (Week 10 slate: 14 games × side, total, moneyline-away, moneyline-home = **56 markets**), with `opening_price` / `opening_captured_at` / `opening_source` / `opening_verification` and the same four `closing_*` columns. |
| `tools/build_price_snapshots.py` | Deterministic, idempotent builder. Seeds captures, resolves the index. Never deletes or edits an existing capture. |
| `tools/record_price.py` | Operational recorder: appends a capture whenever a price becomes available from a source we are entitled to use. Rejects any capture without a real source URL. |

## Recording rules (non-negotiable)

1. **No official or licensed source publishes betting prices** (flag F-06, question Q-02).
   Every price cell that cannot be confirmed from an official source is **blank and flagged** —
   never filled from memory, never inferred.
2. The only capture currently in the store is the **third-party closing line** carried in the
   [nflverse/nfldata](https://github.com/nflverse/nfldata) mirror (`data/processed/schedule_2026.json`),
   recorded with `source_type=third-party-mirror` and `verification=unverified-third-party`.
   It is a benchmark, not a verified fact, and every row that uses it says so.
3. **Opening captures**: none exist. The rows are reserved (blank price, flag `no-opening-capture
   (Q-02)`) so the store is complete by design and fills the moment a feed is connected.
4. Settlement rule for spread captures in this store: the recorded number is the **away team's
   line** (positive = away receiving points); totals are the game total; moneylines are American
   odds for the named selection.

## What this unlocks

* Closing-line value (CLV) measurement per bet once one more capture exists per market.
* Grading of bets at **recorded** prices instead of the assumed −110 used in
  `tools/grade_roi.py` (labelled `assumed_-110` everywhere it appears).
* The G6 economic gate ("edge survives using only release-time best quote") becomes testable.

## The price-data policy decision (N-4, 2026-11-17)

The brief requires a decision on price data **before any backtest is published**. Decided as follows,
and implemented in both price artefacts:

1. **No official price exists, so `market_line` stays blank.** Not "blank until convenient" — the build
   *fails* if a mirror number is ever copied into it (`tools/build_snapshots.py` invariant).
2. **A third-party price may be published, in a channel that names itself.** The snapshot store now
   carries `mirror_close_line`, `mirror_close_source_type=third-party-mirror`,
   `mirror_close_verification=unverified-third-party`, `mirror_close_bytes_sha256` and
   `residual_vs_mirror_close`. 84 of 84 records are priced and labelled; 0 opening captures exist.
3. **The residual is not CLV, and the column says so in words.** No wager was placed at either price, so
   "closing line value" would borrow an authority the data does not have. What is published is the
   arithmetic difference against a named, fingerprinted third-party number.
4. **No opening is ever back-filled from a closing file.** The mirror carries one price set per market;
   a second stage invented from it would be the most flattering cell on the page.
5. **Every price cites bytes, not a URL.** `data/price_snapshots/provenance.json` records the sha256 of
   the pinned mirror file the prices derive from, and `tools/build_snapshots.py` refuses to build when
   the file on disk and `data/raw_manifest.json` disagree — the same rule the results feed now follows
   after the mirror was observed changing between two fetches 21 minutes apart.

Consequence for the backtest published alongside it: the shadow baseline keeps `market_line` and
`residual` blank and is scored on outcomes only (PR-01, unchanged); the residual above is published on
the labelled basis and is never used to rank a strategy.

## Open items (published on Flagged for Review)

* **Q-02** — no licensed price feed. Without one, opening numbers stay blank and CLV cannot be
  computed. Suggestion S-01 (owner decision) covers licensing options.
