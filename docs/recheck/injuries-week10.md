# Injury report — Week 10 (2026): line-by-line re-check ledger (task T9)

**Task:** T9 (takeover) · **Session:** `arena/cc51616e-x1` · **Completed:** 2026-11-14 (UTC)
**Official source (single source of truth):** <https://www.nfl.com/injuries/> — "Official Latest NFL
Injury Report for Players - Week 10 of the 2026 Season | NFL.com"
**File checked:** `data/injuries_2026_week10.csv` (345 rows, 14 games)
**Machine-readable ledger:** [`data/recheck/injuries_week10.json`](../../data/recheck/injuries_week10.json)

## Rule applied

> If a value cannot be confirmed from an official source, the cell stays blank and the item is
> flagged. Nothing is inferred, and no number is invented to fill a table.

## Method

1. The official page was re-fetched on 2026-11-14 in all **8 chunks** (chunkIndex 0–7). Chunks 0–6
   contain the **28 team tables** (14 games); chunk 7 contains news only.
2. **Every printed cell** of every row — player, position, injury, practice status, game status —
   and every **player URL** was compared against the corresponding cell of the official page, row by
   row, in page order. Row counts per team table were reconciled to the CSV.
3. A **programmatic three-way cross-diff** was run between three independent same-day
   transcriptions of the same official page:
   - `data/injuries_2026_week10.csv` (session `c39d8541`, the file under check)
   - `data/nfl/injuries_week10.tsv` (session `b38a21d8`)
   - `data/pipeline/injuries.json` (automated collector, `_retrieved_at` 2026-11-14T17:02:18Z)

   Result: **345/345 keys matched, 0 cell disagreements** after normalising team codes
   (LAR = LA, ARI = AZ, per flags I-15/I-16). This also independently confirmed the fix below.

## Result

| # | Game | Rows | Page chunk(s) | Verdict |
|---|---|---|---|---|
| 1 | WAS at NYG (Thu Nov 12) | 20 | 0 | all cells verified |
| 2 | NE at DET (Sun 9:30 AM) | 24 | 0 | all cells verified |
| 3 | KC at ATL (Sun 1:00 PM) | 24 | 0–1 | all cells verified; **1 URL mismatch corrected (C-01)** |
| 4 | MIN at GB (Sun 1:00 PM) | 30 | 1 | all cells verified |
| 5 | JAX at TEN (Sun 1:00 PM) | 23 | 1–2 | all cells verified |
| 6 | BUF at NYJ (Sun 1:00 PM) | 23 | 2 | all cells verified |
| 7 | MIA at IND (Sun 1:00 PM) | 25 | 2–3 | all cells verified |
| 8 | CAR at NO (Sun 1:00 PM) | 24 | 3 | all cells verified |
| 9 | HOU at CLE (Sun 1:00 PM) | 28 | 3 | all cells verified |
| 10 | LA at AZ (Sun 4:05 PM) | 29 | 4 | all cells verified |
| 11 | SEA at LV (Sun 4:05 PM) | 20 | 4 | all cells verified |
| 12 | SF at DAL (Sun 4:25 PM) | 31 | 4–5 | all cells verified |
| 13 | PIT at CIN (Sun 8:20 PM) | 17 | 5 | all cells verified |
| 14 | LAC at BAL (Mon 8:15 PM) | 27 | 5–6 | all cells verified |
| | **Total** | **345** | 0–7 | **345 verified · 0 unverified · 1 mismatch found and corrected** |

Before this re-check, 44 of 345 rows had been re-checked (WAS at NYG and NE at DET only; flag
I-17 = `needs review`). **I-17 is now resolved:** all 345 rows are re-checked.

## Corrections (evidence-backed, no inference)

### C-01 — Jaylon Moore (KC, T) player URL slug

| | |
|---|---|
| File | `data/injuries_2026_week10.csv` (and its upstream raw file `data/raw/injuries_2026_week10_official.psv`) |
| Row | `KC at ATL · KC · Jaylon Moore · T · Ankle · Did Not Participate In Practice · Out` |
| Field | `player_url` |
| Before | `https://www.nfl.com/players/jaylon-moore/` |
| After | `https://www.nfl.com/players/jaylon-moore-2/` |
| Evidence | Official page (chunk 1) prints `[Jaylon Moore](https://www.nfl.com/players/jaylon-moore-2/)` — <https://www.nfl.com/injuries/> |
| Corroboration | `data/nfl/injuries_week10.tsv`, `data/pipeline/injuries.json`, `data/injuries/injuries_2026_week10.csv` and `data/nfl/availability_derived.tsv` all already carried `jaylon-moore-2` |

No other cell of any of the 345 rows required correction.

## Observations (flagged, not changed)

### R-01 — news headline vs report (needs review)

The official NFL news roundup dated Saturday, Nov 14, 2026 carries the headline *"NFL news roundup:
Colts activate DE Arden Key from IR; Steelers TE Pat Freiermuth (illness) questionable"*
(<https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-saturday-nov-14>), but
**Pat Freiermuth does not appear on the official Week 10 injury report** — the PIT table has exactly
8 rows (Echols, Elliott, Harmon, Heyward, Skowronek, Slaughter, Washington, Watt). The CSV
transcribes the report exactly as printed; neither page states why the two do not reconcile.
**Not corrected** — the report is the registered source for this dataset; the discrepancy is
published here instead of being resolved by inference.

### Pre-existing flags this re-check did not clear (unchanged, see Flagged for review)

| ID | Item (summary) | Source |
|---|---|---|
| I-05 | Puka Nacua: DNP with no injury listed; NFL.com news says likely IR (turf toe, MCL/PCL) | [report](https://www.nfl.com/injuries/) · [news](https://www.nfl.com/news/rams-wr-puka-nacua-likely-to-be-placed-on-injured-reserve-with-turf-toe-sprained-mcl-and-pcl) |
| I-06 | 21 rows: DNP with no injury and no game status; reason not stated | [report](https://www.nfl.com/injuries/) |
| I-07 | BJ Green II (JAX): Full Participation shown with game status Out | [report](https://www.nfl.com/injuries/) |
| I-08 | 3 player-link slugs differ from printed names (Hummel→jake-hummel, Curl→kamren-curl, Dexter Sr.→gervon-dexter); kept as published | [report](https://www.nfl.com/injuries/) |

These are properties of the official page itself — verified present on re-fetch, retained as
published, never "fixed" by inference.

## Verification performed (this session)

| Check | Result |
|---|---|
| Line-by-line cell comparison, all 345 rows vs page chunks 0–7 (2026-11-14) | 345 verified, 0 unverified |
| Row-count reconciliation (28 team tables = 345 rows, 14 games) | pass |
| 3-way cross-diff (CSV vs TSV vs pipeline JSON), 345 keys × 6 fields | 0 disagreements |
| `python3 scripts/verify_data.py` | pass (345 rows, 14 games, auto flags I-05/06/07/08/14) |
| `python3 scripts/check_site.py` | pass (27 pages, links + source links) |
| `python3 tools/verify_data.py` | pass (2,944 assertions) |
| `python3 tools/cross_check.py` | pass (345 injury rows, 1,380 cells, 0 disagreements) |
| `python3 scripts/verify_site.py` | pass (82 HTML pages) |
| `python3 tools/build_site.py` + staleness (`git diff --exit-code`) | pass (root site unchanged) |
| `python3 tools/build_availability.py` + staleness | pass |
| `python3 scripts/build_site.py` (dashboard regenerated after the correction) | pass; `scripts/check_site.py` re-run after regeneration: OK |

Note: `tools/check_links.py` currently fails on `main` with 111 pre-existing failures unrelated to
this task (the `live/` section's stylesheet/nav/snapshot contract and JS template-literal hrefs).
That defect is claimed by two other sessions (A7 / T10 on the coordination board); this session did
not touch the checker. Diagnosis was reported to the board for them.

## Files changed by this task

| File | Change |
|---|---|
| `data/raw/injuries_2026_week10_official.psv` | 1 cell: `jaylon-moore` → `jaylon-moore-2` (upstream of the CSV) |
| `data/injuries_2026_week10.csv` | regenerated from the raw file by `scripts/verify_data.py`; exactly 1 line differs |
| `data/sources.csv` | S03 note updated to record the completed re-check |
| `scripts/build_site.py` | `CHECKED_GAMES` = all 14 games; I-17 status text → resolved; chips/texts updated (T9 status only) |
| `dashboard/*.html` | regenerated by `scripts/build_site.py` (not hand-edited) |
| `docs/recheck/injuries-week10.md` | this ledger (new) |
| `data/recheck/injuries_week10.json` | per-row machine-readable verdicts (new) |
