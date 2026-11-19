# Round 9 — targeted fixes for R8-I-05, R8-I-06 and R8-I-07

**Reviewed:** 2026-11-19 UTC  
**Branch:** `arena/ab244ddc-x1`  
**Scope:** published replacement-depth names/method and retrospective leaderboard leakage. This is a repository repair of already source-linked records, not a fresh 32-club source recapture.

## Changes

| Finding | Change | Source/provenance | Verification and caveat |
|---|---|---|---|
| R8-I-05 — Green Bay display names include leading jersey numbers | The replacement-depth builder now exposes a `strip_jersey()` display normalization for leading jersey-number prefixes, while retaining the exact original text in `starter_raw` and `replacement_raw`. The published CSV/JSON were transformed without dropping or otherwise altering the existing 78 source-linked records: 7 rows had a printed prefix removed; all raw strings are retained. Depth order continues to be taken from the club chart's printed order, never from the jersey number. | [Packers official depth chart](https://www.packers.com/team/depth-chart); [NFL official injury report](https://www.nfl.com/injuries/). Each published row keeps its club-chart and NFL injury-report URLs. | Checked CSV/JSON row-count parity (78), identical field order, 7 changed display rows with raw string retained, and zero display names beginning with a digit. The official pages were not re-fetched for this parser-only repair; all underlying values remain those of the previously retained, source-linked capture. |
| R8-I-06 — method claims a single starter is “column 1” | The generated summary now describes depth slots as groups, avoids fabricating one starter where the official chart shares rank 1, and states that replacement string follows club-printed order. The method links to the repo's 32-club depth-slot-group register. | [NFL official injury report](https://www.nfl.com/injuries/); club chart URLs are retained per row; [32-club depth group register](../../data/depth/depth_groups_32.csv). | Ran `python3 tools/build_round3.py --check` and reviewed the rebuilt method. That command compares tracked outputs with `HEAD`; until this fix is committed it reports the expected source diff. The workflow result must be rechecked after commit. |
| R8-I-07 — retrospective walk-forward numbers displayed in leaderboard | Removed `DIAG-WF-SHRINKAGE-W1-10` from the leaderboard. Also cleared retrospective result metrics from all three control rows (not only the diagnostic model). Moved the model diagnostic and control results into `data/origination_desk/skill/diagnostic_walkforward.csv`, explicitly marked audit-only/excluded from leaderboard. The generated leaderboard page now distinguishes this detached archive from prospective competition entries. | [Official NFL Week 10 schedule/results](https://www.nfl.com/schedules/2026/by-week/week-10); [official 2026 standings](https://www.nfl.com/standings/league/2026/REG). | `verify_desk.py` now asserts diagnostic ID absence from the leaderboard, blank retrospective metric cells for all control rows, and four detached audit rows. `build_skill_desk.py`, `build_site.py`, and `verify_desk.py` passed; 1,631 checks passed. The retrospective scores are retained for audit, not claimed as independently re-verified during this parser/site repair. |

## Important capture limitation

`tools/build_replacement_depth_store.py` consumes the current `data/pipeline/` inputs, which have advanced to Week 11, while the published 78-row replacement-depth artifact is a retained earlier capture. Running the builder in this workspace regenerated only one row and dropped 77 records during its existing re-verification against the newer inputs. Those source-linked published records were restored before editing; the repair was applied as a lossless display transformation. Do not claim that a Week 11 rebuild reproduced the older 78-row capture. A future refresh should be run against matching dated source snapshots, or the builder should be made point-in-time aware.

## Verification performed

- `python3 -m py_compile tools/origination_desk/build_skill_desk.py tools/origination_desk/verify_desk.py tools/origination_desk/build_site.py` — pass.
- `python3 tools/origination_desk/build_skill_desk.py` — regenerated 7 skill data artifacts including the detached diagnostic CSV.
- `python3 tools/origination_desk/build_site.py` — regenerated 8 origination-desk pages.
- `python3 tools/origination_desk/verify_desk.py` — pass, 1,631 checks.
- `python3 tools/origination_desk/build_skill_desk.py --check` — pass.
- `python3 tools/origination_desk/build_site.py --check` — pass.
- `python3 tools/build_app.py` — regenerated the unified dashboard; only `app/replacement-depth.html` changed, showing the cleaned display names. No index/nav files changed.
- `python3 tools/verify_app.py` — pass (29 pages, 1,147 internal links, 8,523 data rows; 0 unsourced).
- `python3 tools/verify_stores.py` — pass, including 78 replacement-depth rows.
- `python3 tools/verify_new_data.py` — pass.
- `python3 tools/build_round3.py --check` — expected to detect the changed committed summary relative to pre-fix `HEAD`; the method rebuild itself succeeded. Re-run once the updated summary is committed.

## Remaining irregularities

- The Week 11 pipeline inputs are not a point-in-time replacement for the older source capture. A dated rebuild is needed to verify all 78 records against their matching source versions.
- The Texans' image-based chart remains outside this fix; no values were transcribed by eye.
- Existing `F-01`/Round 8 documentation may still describe the Packers display prefix as an outstanding parser irregularity. The source format remains the same, but the public display normalization/raw preservation is now implemented; shared flags/index are left for final integration because they are shared outputs.
- No claim is made here about the live GitHub Pages deployment; full workflow, PR, merge and deployment checks remain pending.
