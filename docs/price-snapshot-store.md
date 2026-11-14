# Price-snapshot store

Session `arena/907c5baf-x1` · task N2 · 2026-11-14

## What it is

A store that records an **opening** and a **closing** snapshot for every market we
originate, in origination order — **side (spread) first, then the total, then the
moneyline** — with the model's fair line, the market line and the difference published as
three separate columns.

- Data: [`data/price_snapshots.json`](../data/price_snapshots.json)
- Generator: [`tools/build_price_store.py`](../tools/build_price_store.py)
- Published page: `app/prices.html`
- Methodology of the fair line: [line origination](methodology/line-origination.md)

## Snapshot lifecycle

| Event | What is recorded |
|---|---|
| Origination | opening snapshot: our fair line and our price, timestamped |
| Kickoff | closing snapshot; a missed capture is recorded as **missed**, never back-filled |
| Settlement | the results feed grades the market at both numbers (see [results feed](results-feed.md)) |

## What is in the store today (2026-11-14)

- 56 rows: 14 Week 10 games × 4 originated numbers (spread away, game total, two
  moneylines), ordered side → total → moneyline within every game.
- **Our numbers are filled**: they are reproducible outputs of the published model
  (`code/build_lines.py`), not market facts.
- **Market numbers are blank and flagged**: no official source publishes betting prices
  (flag F-06 / question Q-02). Per the brief's rule, a value that cannot be confirmed
  from an official source is left blank and flagged — never inferred or filled in. The
  difference columns stay blank with them, because a difference needs both inputs.
- The Week 10 Thursday game's close was **missed** (the store was created after kickoff);
  it is recorded as missed.

## Quarantine

Community-mirror price files exist (`data/raw/nflverse/initial_lines.csv`,
`closing_lines.csv`, `games.csv`) and their counts and provenance are recorded in the
store's `quarantine_mirror` block. They are a GitHub mirror, not a book or the league
(I-10 / F-06), so they are never rendered as market prices and never used in a
difference column.

## Source links for manual review

- Kickoff times: <https://www.nfl.com/schedules/2026/by-week/week-10>
- Fair-line method inputs: <https://www.nfl.com/standings/> · <https://www.nfl.com/injuries/>
- Mirror provenance (quarantined): <https://github.com/nflverse/nfldata/blob/master/DATASETS.md>
