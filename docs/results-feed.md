# Verified results feed

Session `arena/907c5baf-x1` · task N1 · 2026-11-14

## What it is

A machine-readable feed of 2026 NFL regular-season results where **every score was
transcribed from the official NFL.com weekly schedule page** and every row carries the
URL it came from. The feed is what makes backtests and ROI computable at all: a market
we originate is graded only against a score the league itself printed.

- Data: [`data/results_feed.json`](../data/results_feed.json)
- Raw transcription: [`data/verify/raw/nfl_scores_2026_official.psv`](../data/verify/raw/nfl_scores_2026_official.psv)
- Generator (reproducible): [`tools/build_results_feed_907c.py`](../tools/build_results_feed_907c.py)
  — renamed twice during PR #40 integration merges as concurrent sessions landed their own
  generators at the obvious names (session `arena-1d3600f8-x1`'s at `tools/build_results_feed.py`,
  session `arena/bf27a3bd-x1`'s at `tools/build_results_feed_official.py`). All feeds are published
  side by side on `app/results.html`; none discards another.
- Published page: `app/results.html`

## Verification performed (all reproducible)

| Check | Result |
|---|---|
| Games transcribed from official pages, weeks 1–10 | 150 (137 FINAL, 13 scheduled) |
| Per-team W-L-T, PF, PA recomputed from the feed vs the [official standings](https://www.nfl.com/standings/) | **32 of 32 clubs match exactly**, 0 mismatches |
| Community-mirror scores ([nflverse/nfldata](https://github.com/nflverse/nfldata/blob/master/data/games.csv)) vs the official page | 137 compared, 137 agree, 0 disagree |
| Week 10 originated markets settled from the official final (WAS 24 @ NYG 21, [game page](https://www.nfl.com/games/commanders-at-giants-2026-reg-10)) | 6 legs graded: 3W-3L |

The standings cross-check is the strong one: 137 independent transcribed scores
reproduce every club's official record **and** points for/against to the digit. A single
misread score would break a PF/PA identity for at least one club.

## Settlement rules

1. A result is graded only after the official page prints **FINAL**. Unplayed games keep
   blank results and a flag; nothing is inferred.
2. ROI is computed only from legs whose price we originated ourselves (the moneyline
   legs). Spread and total legs currently have **no originated price** — the price
   authority question (Q-31) is open — so no ROI is published for them.
3. Every ROI is published with its **n**. The Week 10 sample is n = 1 game; the number is
   arithmetically correct and statistically meaningless, and the feed says so.

## Deliberate limitations

- Seasons 2006–2025 exist only in the community mirror (`data/raw/nflverse/games.csv`).
  They are used for labelled backtests and are **not** game-by-game verified against
  NFL.com (flag I-11). They are never rendered as fact.
- A mirror agreement (137/137) is corroboration, not proof: a shared upstream mistake
  would not be caught (same blind spot the cross-check page records as F-13).

## Source links for manual review

- Week pages: <https://www.nfl.com/schedules/2026/by-week/week-1> … <https://www.nfl.com/schedules/2026/by-week/week-10>
- Standings: <https://www.nfl.com/standings/>
- The single graded game: <https://www.nfl.com/games/commanders-at-giants-2026-reg-10>
