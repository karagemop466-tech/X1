# 2026-11-18 reads pack — session `arena/91656714-x1` (round 6)

This pack is the **independent third read** of the two official pages the results feed is settled
against. It exists so the Week 10 closure (13 games promoted from `SCHEDULED` to `FINAL`) is not
accepted on one session's word.

| File | What it is | Official source |
|---|---|---|
| `official_w10_finals_2026_11_18.tsv` | 14 Week 10 fixtures as printed on 2026-11-18, with the club records printed beside each club | https://www.nfl.com/schedules/2026/by-week/week-10 |
| `official_standings_2026_11_18.tsv` | 32 clubs, legend-defined columns only | https://www.nfl.com/standings/ (league table at /standings/league/2026/REG) |
| `official_gamecentre_LAC_BAL_2026_11_18.md` | the one fixture that turned the week from 13 finals to 14, verified at its own Game Center page | https://www.nfl.com/games/chargers-at-ravens-2026-reg-10 |

Checker: `tools/verify_2026_11_18.py` (33 checks). It cross-compares this pack against the
2026-11-16 and 2026-11-17 packs cell for cell, and — the part that makes "verified" mean something —
recomputes all 32 clubs' W-L-T / PF / PA **from the published feed itself** and requires the official
standings table to match (B7). A wrong promoted score moves a club's PF/PA and B7 fails.

## Result on 2026-11-18

- 14/14 Week 10 fixtures agree across three independent reads.
- 32 clubs × 10 columns agree with the 2026-11-17 read: **0 cell mismatches**.
- 11-16 vs 11-18: only BAL and LAC differ, only in the cells the Monday result touches (correct
  point-in-time behaviour, not a conflict).
- Feed-vs-official: **150 scored games → 160 cells, 0 clubs disagree**.
- Shadow baseline arithmetic reproduces at full precision; game-cluster 95% lower bound **-0.0052**
  is published as it computes (it crosses zero).

## Limits of this pack

- It is a *third read by a machine-assisted fetch*, not a re-transcription from PDF bytes. The
  retained-byte evidence for the mirror is `data/raw_manifest.json` (sha256 pinned); the official
  pages have no byte-level capture here (flag X-13).
- The weekly page prints a venue only for the Munich international game, so no venue column exists
  in the finals pack. Venues belong to each fixture's Game Center page.
- Kickoff time and network are blank: this read's parsed text did not print them for completed
  games. Blank means "not printed by this read", never "unknown, filled in from elsewhere".
