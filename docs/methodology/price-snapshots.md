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

## Open items (published on Flagged for Review)

* **Q-02** — no licensed price feed. Without one, opening numbers stay blank and CLV cannot be
  computed. Suggestion S-01 (owner decision) covers licensing options.
