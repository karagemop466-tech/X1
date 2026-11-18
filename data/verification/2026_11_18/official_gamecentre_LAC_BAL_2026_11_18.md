# Official Game Center — LAC at BAL, 2026 REG Week 10

**URL:** https://www.nfl.com/games/chargers-at-ravens-2026-reg-10
**Page title:** "Los Angeles Chargers at Baltimore Ravens 2026 REG 10 - Game Center"
**Read:** 2026-11-18, ~03:30 UTC, by session `arena/91656714-x1` (platform fetch tool, chunk 0 of 2).

This fixture is the one that turned Week 10 from 13 finals into 14. It is verified at its own
Game Center page, not only on the weekly schedule page, because it is the single row whose promotion
changes the results feed's coverage claim.

## Strings printed by the page, verbatim

| Printed string | What it evidences |
|---|---|
| `LAC … 23 … 23 points … Winner Indicator` | away_score = 23, away side won |
| `BAL … 20 … 20 points` | home_score = 20 |
| `Final` | status = Final |
| `WEEK 10` / `Nov 16` | the fixture's week and date |
| Q1 `10` / `0`, Q2 `7` / `10`, Q3 `3` / `3`, Q4 `3` / `7`, TOTAL `23` / `20` | quarter splits sum to the final, 23 = 20 + 3 and 20 = 20 |
| `Location LOCATION BALTIMORE, MD` | venue city/state |
| `Stadium STADIUM M&T BANK STADIUM` | venue name |

## Arithmetic check performed

10 + 7 + 3 + 3 = 23 and 0 + 10 + 3 + 7 = 20. The quarter splits printed by the page sum to the
totals printed by the page, so the total is internally corroborated rather than read once.

## What this page does NOT establish

- It is **one fixture**. It does not evidence the other 13 Week 10 games; those are evidenced by the
  weekly schedule page (`official_w10_finals_2026_11_18.tsv`).
- The page links a "Download Game Book (PDF)" (`static.www.nfl.com/image/upload/v1794916121/...`).
  This round did not fetch or retain those bytes, so there is **no hash** for it here. Flagged X-13.
- Venue is printed for this fixture only because a Game Center page prints it. The weekly page does
  not, so venue remains absent from the other 13 rows rather than inferred.
