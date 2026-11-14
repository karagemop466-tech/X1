# Origination order and the three-column rule (T17)

**Session `arena-1d3600f8-x1` · 2026-11-14**

## What the owner asked for

> Originate the side first, then the total, then the moneyline.
> Publish the model's fair line, the market line, and the difference as separate columns.

## Origination order (now codified)

Markets are originated and published in a strict sequence:

| origin_seq | origin_order | Market | Selections |
|---|---|---|---|
| 1 | **side** | spread | away (the side market is one market; our number is the away line) |
| 2 | **total** | game total | over (the total market is one market; our number is the total) |
| 3 | **moneyline** | moneyline | away, then home |

The reason for the order: the side is the deepest, most liquid market and the one the model is
fitted against; the total is derived from the same points model and must not be tuned to the
side's residual; the moneyline is derived from the side/total joint outcome distribution and is
therefore originated **last**, so it can never influence the other two.

## The three-column rule

Every originated market publishes three **separate** columns — never combined, never parenthesised
into one cell:

* `fair_line` — the model's own number (our computation, published as such);
* `market_line` — the market capture from the price-snapshot store, with its provenance and
  verification status carried alongside; blank + flagged if no source exists;
* `difference` — `fair_line − market_line`, in the market's own units (points for side/total;
  odds points for moneyline) — the unit is published in `difference_unit`.

## Where

* `data/lines/origination_2026_week10.csv` — 56 rows (14 games × side, total, ML-away, ML-home),
  sorted by origin_seq, built by `tools/build_origination_table.py` from
  `data/lines/originated_lines_2026_week10.csv` (fair lines) and
  `data/price_snapshots/market_index.csv` (market captures).
* All 56 rows currently carry all three columns filled; the market column is flagged
  `unverified-third-party` (nflverse mirror benchmark) because **no official source publishes
  betting prices** (Q-02 / F-06).

## Conventions (fixed, documented, tested)

* Spread: the **away team's line** — positive = away receiving points. (Matches
  `market_spread_away` in the originated lines CSV and `spread_line` in the mirror.)
* Total: the game total; difference positive = model expects more scoring than the market.
* Moneyline: American odds per selection; difference in odds points.
