# Venue and fixture context: how these cells are produced

Dated 2026-11-18, session `arena/efb06932-x1` (round 6). Applies to:

* `data/official/gamecentre/venue_register_latest.tsv` — 27 fixtures, 35 columns
* `data/official/fixture_context/fixture_context_2026_w11.csv` — 13 fixtures, 30 columns

The brief's rule governs everything below: *every value must be verified against an official source,
and anything that cannot be verified stays blank and gets flagged.* For a venue table that rule has a
consequence worth stating plainly: the league's Game Center page prints two facts about the building
— a Location and a Stadium — and nothing else. So this register publishes two verified columns and a
set of blanks that say why they are blank. Capacity, roof, surface, attendance, weather and
officiating are **not** in the source, and they are not filled from a team site, a stadium wiki, or a
previous season's page. A blank cell with a flag is a finding; a plausible number is a hallucination.

## 1. The source and how it is fetched

| | |
|---|---|
| Fixture set | `https://www.nfl.com/schedules/2026/by-week/week-10` and `.../week-11` |
| Per-fixture page | `https://www.nfl.com/games/<away>-at-<home>-<season>-reg-<week>` |
| Runner | `tools/official/gamecentre.py` |
| Scheduled by | `.github/workflows/game-centre-venue-capture.yml` (push and 03:00 UTC cron) |
| Last capture | `2026-11-18T03:26:54Z` — 27 rows, 27 expected, 0 fetch errors |

The runner shares `pipeline/http.py` with the results pipeline, so it inherits retry, exponential
backoff, `User-Agent`, `Accept-Encoding: gzip`, `robots.txt` and rate-limit handling, and it stops on
`403`/`404` rather than hammering. Every URL's HTTP status, byte count and attempt count is recorded
in `venue_report.json`, so "we read it" is a claim with a receipt. The fixture list is read from the
league's own week page — not from a roster of games we intended to look at — so a rescheduled or
added fixture shows up as a count change (`rows_expected`) rather than a silent omission.

## 2. What is retained, and why that is the whole point

Each page is kept, gzipped, under `data/official/gamecentre/raw/` with its SHA-256 recorded in the
row (`raw_gz_sha256`, and `body_sha256` for the decompressed text). 6.35 MB of gzip backs 27 rows.

This is what makes the register auditable after the fact, including by someone who cannot reach the
league page: the parse is a function of bytes that are in the repository. `reparse` re-runs the parser
over the retained bytes and republishes; `verify` re-derives the published cells from those bytes and
fails if they disagree. A parser fix therefore changes the register **against a hash that does not
move**, which is the only way to distinguish "the page changed" from "we changed our reading of it".

## 3. How the parse works, and the two defects that made it stricter

Lines are normalised by keeping block boundaries (`norm_lines`), then `Label value` /
`Label LABEL value` / `Label` + next-line patterns are matched against a known-label list. Entities are
decoded after tag-stripping. The `__NEXT_DATA__` JSON is used only when the printed block is absent.

Two defects were found, both by *comparison*, not by inspection:

1. **False `FINAL` on 13 unplayed fixtures.** The first parser searched the whole page for a status.
   The word `FINAL` also appears in a standings table further down the page, so every Week 11 fixture
   — not yet played — was published as final. Fix: status, period, clock and scores are read only from
   the score box above the `Game Info` anchor (`scorebox_lines`, a bounded window). If no status line
   appears in that region, the cell is blank and the row is flagged
   `no-status-line-before-game-info`. Scores are blank on every row and flagged
   `scores-not-in-text-layer`, because the page renders them inside elements whose text layer prints
   the literal string `Hidden Score`.
2. **`AT&amp;T STADIUM`.** Tag-stripping leaves HTML entity references in the text, which affected two
   of the 27 rows — including a stadium name the hand register already had right.

Both are now guarded by `selftest`, which asserts against page shapes: a final page, a live page, a
scheduled page (status *must* stay blank), and a page with no Game Info block at all (nothing may be
invented). `selftest` is offline and runs in CI before any network step, so a parser change cannot
ship without passing these cases.

## 4. Cross-checks: two independent reads, never a merge

`cross-check` compares, and does not copy:

* **Stadium vs the hand transcription** of the same official pages
  (`data/nfl/venues_2026_week10.csv`, PR #86/#87, session `arena/5433abad-x1`):
  **14 of 14 cells agree, 0 differ** (it was 12/14 before the entity fix — the comparison is what
  found that bug). Slug keys are normalised (`base()`) because the runner keeps the season/week suffix
  and the hand register does not.
* **Fixture set vs the collector's own dated slate read**
  (`data/lab/reads/2026-11-17/week11_slate_2026-11-17.tsv`, read `2026-11-16T18:52:00Z`):
  **13 captured, 13 on the slate**, no set difference.

The recorded rule is the one the brief demands: *a difference is a finding for the Flagged page, never
a value to copy over.* The result is committed as `fixture_crosscheck.json` and its mismatch count is
printed in CI; a non-zero count does not fail the capture — a broken site is not fixed by hiding the
disagreement — but it does put the row in front of a human.

`drift` compares the retained parse with the previous register for the same fixtures and reports
field-level changes (`venue_report.json` → `drift: []` today). The drift alarm's job is to answer "did
the page change, or did our reader change?" and it can only do that because the bytes are retained.

## 5. Per-cell provenance columns

Each row carries the method as well as the value, so a reader can see how much to trust a cell:

| Column | Values seen today | Meaning |
|---|---|---|
| `venue_method` | `label-line` × 27 | read from the printed label/value lines |
| `status_method` | `scorebox` × 27 | read from the bounded region above `Game Info` |
| `score_method` | `none` × 27 | no score exists in the text layer |
| `parser_version` | `r6-2026-11-18-scorebox-bounded` × 27 | which reader produced the cell |
| `flags` | `final-without-score`, `scores-not-in-text-layer`, `surface-not-on-page`, `roof-not-on-page` | what the row does not know |

`verify` re-derives nine of these columns per row — 243 cell re-derivations today, 0 mismatches,
verdict PASS (`verify_report.json`).

## 6. Fixture context: features from published schedule facts only

`tools/official/fixture_context.py` joins the venue register with the dated slate reads to produce, per
fixture: kickoff and network, both records as read, rest days and short-week and bye markers, previous
venue, same-city-as-previous, `international`, `prime_time` (derived from the slate's own window label,
not from a kickoff-time threshold), roof and surface.

Today: 13 rows, **13 with a stadium** (via the capture), rest days for 12 away and 10 home, and
**0 roof and 0 surface** — because, again, the page does not print them. The four blank rest-day cells
are not missing reads: a bye in the prior week means there is no previous fixture to count days from,
which is a fact about the schedule and is written as `rest-days-unknown:*` so nobody mistakes it for a
gap in coverage. `international` is `yes` for exactly one Week 11 fixture — `MIN@SF` at
`ESTADIO BANORTE`, `MEXICO CITY` — from the league's international schedule, and the Munich row in
Week 10 carries Location `MUNICH`, Stadium `FC BAYERN MUNICH STADIUM`.

The one structural limit to keep in view: the register covers 27 of 285 season fixtures (Weeks 10 and
11). Widening it is suggestion **SG-16**, with a retention decision attached — a full-season capture is
~350 MB of gzip per run, which is not sustainable in a Pages repository, so the recommended path keeps
raw bytes only for fixtures that enter a feature set and flags every row whose bytes were dropped.

## 7. Reproducing any number on this page

```
python3 tools/official/gamecentre.py selftest      # page-shape cases, offline
python3 tools/official/gamecentre.py capture        # network; writes the register + raw/ + report
python3 tools/official/gamecentre.py reparse        # republish from retained bytes only
python3 tools/official/gamecentre.py verify         # cell-by-cell re-derivation
python3 tools/official/gamecentre.py cross-check    # against the hand register and the slate
python3 tools/official/fixture_context.py build && python3 tools/official/fixture_context.py check
```

The site tables that publish these numbers are `console/venue-capture.html`
(`data/official/gamecentre/`), built by `tools/build_console.py` from the same files, never from a
copy of them.
