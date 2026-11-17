# Staleness audit — 2026-11-17

**Session:** `arena-2f95e652-x1` · **Pack:** `data/evidence/2026_11_17/` · **Read (UTC):** 2026-11-17T22:46Z

This memo records what a dated read of the official pages found when it was compared with the
tables this repository publishes, and what was fixed. It exists because the console published a
verification claim that was not reproducible, and a claim like that is worse than no claim: it
tells a reader not to check.

---

## 1. The false claim (fixed in this session's evidence pack; the page text is an integration request)

`console/standings.html` printed:

> All 32 clubs and all 16 fields were re-read from the league's own standings table on the build
> date and matched the published table with no mismatches.

and a KPI reading **512 comparisons — re-read today, 0 mismatches**.

That is not what the generator does. `tools/build_console.py` compares nothing at build time:

```python
STANDINGS_RECHECK = {"rows": 32, "fields": 16, "comparisons": 512, "mismatches": 0}
```

is a literal, and the KPI renders `STANDINGS_RECHECK["comparisons"] - STANDINGS_RECHECK["mismatches"]`.
The table it renders is `data/verify/official_standings_2026_w10.psv`, a transcription dated
**2026-11-14** which states in its own header that only the Week 10 Thursday game was final.

So the published comparison was *a snapshot against itself*, presented as *a snapshot against
today*.

## 2. What a real read of today's page says

Read at 2026-11-17T22:46Z from
<https://www.nfl.com/standings/league/2026/REG>, transcribed row by row:

| measure | value |
|---|---|
| clubs read | 32 of 32 |
| fields read per club | 17 transcribed, 15 published (2 withheld, see §4) |
| games played implied by the league's own W/L/T | **150** |
| games played implied by the published 2026-11-14 table | 137 |
| cells where the published table disagrees with today | **262 of 448** |
| clubs affected | **26 of 32** |
| cells where the collector's independent parser disagrees with this read | **0 of 544** |

The 262 differences are *games played*, not transcription errors. The 2026-11-14 table was
correct when it was taken. The defect is the word "today".

### The arithmetic that validates the read before it accuses anything

Applied to the new read first, so a mis-transcription cannot be published as someone else's error
(`data/evidence/2026_11_17/closure.tsv`):

| check | result |
|---|---|
| wins == losses | 149 vs 149 — pass |
| ties even | 2 — pass |
| points for == points against | 6923 vs 6923 — pass |
| net points sum to zero | 0 — pass |
| PCT and NET recompute from printed W/L/T/PF/PA | all 32 rows — pass |
| home+road, conf+non-conf, div ≤ conf, streak and last-5 shapes | all 32 rows — pass |
| the 14 Week 10 finals added to the 2026-11-14 table reproduce today's table | 160 comparisons, **0 mismatches** |

That last row is the strong result: one read of the standings and one read of the scoreboard,
taken independently, agree on 32 clubs × 5 fields. It also caught its own first-draft error — the
Thursday game (WAS–NYG, 2026-11-12) was **already inside** the 2026-11-14 table, so adding all 14
finals double-counted it and produced six false mismatches on WAS and NYG. The pack now carries an
explicit `in_2026_11_14_snapshot` flag per game rather than a date heuristic, and
`tools/verify_evidence_2026_11_17.py` fails if that flag is wrong.

## 3. The drift alarm that nothing consumed (fixed)

`data/captures/index.jsonl` carried `"drift": "fail"` on the `deficiency` capture:

```
declared-columns-mismatch: the payload declares 12 columns and its rows carry 14 keys;
undeclared in the rows: ['depth_listed', 'team_abbrev']
```

Cause: `pipeline/run.py` built 14 values per row and declared 12 columns. The rows were right;
the header was wrong. Three changes:

1. **Producer fixed** — `pipeline/run.py` now declares all 14, in the order it builds them, and
   the committed `data/pipeline/deficiency.json` was regenerated with the same header.
2. **Gate made load-bearing** — `scripts/pipeline/verify_captures.py` used to treat
   `declared-columns-mismatch` as alarm-only, which is why a real defect sat in the published
   status file while the site showed eight unrelated flags. It now applies the pin to the
   **committed producer output**, where a pull request can actually fix it. Proven both ways:
   the mutation test catches it (`--self-test` → 6/6), and re-breaking the committed file makes
   the gate exit 1.
3. **The capture-side alarm is kept, and distinguished** — a retained capture cannot be re-taken
   from a pull request, so a capture-side alarm whose producer is already clean is reported as a
   *stale alarm* and clears on the next collector read. It is not silently dropped.

## 4. What this read could not confirm (withheld, not inferred)

`DIVPCT` and `CONFPCT` are printed by the league's page, but the text extraction used here rendered
them inside the adjacent split-record cell. They are **withheld**: the column is omitted from
`standings.tsv`, and every diff against the published table prints `(withheld)` on the read side.
They are not recomputed from W/L/T, because publishing arithmetic as if it were a read is exactly
the failure this repository is built to avoid. `tools/verify_evidence_2026_11_17.py` enforces that
no withheld field appears as a column and every other field is non-blank.

## 5. Two things this pack proves the site cannot do yet

Both are limitations of the sources, not repair items for a pull request:

| question | measured answer |
|---|---|
| Has the mirror behind the results feed published the Week 10 finals? | **1 of 14** Week 10 rows carries a score in `data/raw/nflverse/games.csv`. The results feed is built from that file, so Week 10 cannot settle, and neither the 2026 ROI nor the pre-registered shadow baseline can advance, until the mirror publishes. |
| Can 2026 lines be re-originated against a closing price? | **0 of 704** 2026 price-store rows carry both ends (step 1: 189 rows, step 2: 189, step 3: 326; all opening-only). Origination is pre-kickoff by definition; a 2026 market originated today can only carry the opening number until a read is taken at kickoff. |

## 6. A scheduled workflow has been failing on every run (fixed)

`Refresh research data` (`.github/workflows/pipeline.yml`, TUE/FRI cron) declares
`permissions: contents: write` but ends with `peter-evans/create-pull-request@v6`, which needs
`pull-requests: write`. Run
[44123337794](https://github.com/karagemop466-tech/X1/actions/runs/44123337794) (2026-11-17 06:23Z)
shows the pipeline and site rebuild both **succeeding** and then `Resource not accessible by
integration` at the PR step — the refreshed artefacts were produced and thrown away. The permission
is now widened to the minimum that lets the step run; the next scheduled run is the proof.

## 7. Integration requests (files owned by another session's claim)

`tools/build_console.py` is claimed by open PR #61, so this session did not edit it. These are the
edits the console needs, written so they can be applied on top of #61's version:

1. **Delete the false claim.** In `build_pages_2`, drop `STANDINGS_RECHECK` and replace the
   standings KPI/note with the dated wording: the table is the 2026-11-14 official transcription
   (137 games through the Week 10 Thursday game), it is not a live feed, and today's league table
   differs on 262 of 448 cells across 26 clubs — see the evidence pack.
2. **Link the pack.** Add an `Official data` nav entry for `evidence-2026-11-17.html` and copy
   `data/evidence/2026_11_17/page.html` into `console/` under that name, with `assets/` rewritten
   as the other console pages do.
3. **Publish the drift state.** `console/flagged.html` currently lists 8 flags and does not
   mention the capture-drift alarm. `src/console/evidence_2026_11_17.drift_state()` returns it in
   the shape flags need.
4. **Re-derive, do not retype.** If a later session re-reads the page, change
   `READ_UTC`, the literals in `src/console/evidence_2026_11_17.py` and re-run
   `tools/build_evidence_2026_11_17.py`; `--check` and the verifier will catch a partial edit.

## 8. Reproduce

```bash
python3 tools/build_evidence_2026_11_17.py --check     # committed pack reproduces
python3 tools/verify_evidence_2026_11_17.py            # every published number re-derived
python3 scripts/pipeline/verify_captures.py --no-freshness   # 0 build-failing, 0 stale
python3 scripts/pipeline/verify_captures.py --self-test      # 6/6 mutations caught
```
