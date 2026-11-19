# Independent current-checkout audit — 2026-11-19

**Session:** `arena/9faff167-x1`  
**Scope:** offline repository integrity checks plus a spot read of the official NFL pages listed below. This is an audit of the checked-in snapshot, not a full row-by-row live recapture. No source data, model output, or generated site page was changed.

## Findings

| ID | Finding | Evidence | Suggested action |
|---|---|---|---|
| IA-F1 | The README says the entire repository is a Week 10 snapshot dated 2026-11-14. That is no longer an accurate repository-wide freshness statement: the tree includes a separately dated 2026-11-19 official Week 11 verification pack and Week 11 injury capture. | `README.md` → “Data snapshot”; `data/verification/2026_11_19/verification_summary_2026_11_19.json`; `data/verification/2026_11_19/official_w11_injuries_2026_11_19.tsv` | Replace the global date claim with a per-dataset freshness rule and point users to each dataset's captured-at/source metadata. Do not imply the whole repository is current merely because one dataset is recent. |
| IA-F2 | `python3 tools/verify_2026_11_19.py --check` passes its measurement comparison but rewrites `generated_at` in the tracked verification summary. The comparison deliberately removes that field, so the values match, but the nominal check has a working-tree side effect. | `tools/verify_2026_11_19.py` lines 419, 455–460; the observed diff changed only `generated_at` from `06:56:46Z` to `19:24:04Z`. The file was restored after the check. | Make `--check` read-only (compare an in-memory fresh result, without writing), or clearly label it as a rebuild-and-compare command. Add a mutation test asserting the worktree remains clean. |
| IA-F3 | The existing Week 11 pack is a reproducible, internally consistent frozen read; its `--check` is not a live web re-fetch or a fresh cell-by-cell comparison against the NFL pages. | `--check` implementation reads and rewrites the local summary; live source URLs are in the captured pack. The live official pages were separately opened for this audit. | Keep the capture date and method adjacent to every live-looking table. For a new verification claim, fetch and retain a new dated capture first, then run the row-level diff. |

These are documentation/verification-process findings, not evidence that a published NFL fact is wrong. The official report itself includes anomalies already identified in the repository; those remain unresolved and should stay flagged rather than silently “corrected.”

## Official sources opened for a spot read

- [NFL 2026 regular-season league standings](https://www.nfl.com/standings/league/2026/REG)
- [NFL 2026 Week 11 schedule](https://www.nfl.com/schedules/2026/by-week/week-11)
- [NFL 2026 Week 11 injury report](https://www.nfl.com/injuries/league/2026/reg11)

The fetch tool returned the official pages on 2026-11-19 UTC. This spot read confirms that the cited pages are the current official pages for the 2026 standings, Week 11 slate, and Week 11 report. It does **not** certify every archived row against the live page. The checked-in pack itself records its own read date, source links, totals, alias notes, and named irregularities.

## Repository checks run

All commands completed successfully on the checked-out tree:

| Check | Result |
|---|---|
| `python3 tools/verify_data.py` | 2,960 integrity checks passed |
| `python3 tools/check_links.py` | 211 files; 50,773 assertions; links resolve, approved external hosts, no orphan pages |
| `python3 scripts/verify_site.py` | 211 HTML pages; local links resolve; table rows are sourced or explicitly flagged |
| `python3 tools/verify_app.py` | 29 pages; 8,260 data rows; 8,236 source-linked; 24 explicitly flagged as lacking a source; 0 unflagged unsourced rows |
| `python3 scripts/verify_research_site.py` | 16 files; 2,006 assertions; 4 tests passed |
| `python3 tools/verify_stores.py` | Results, price-store ordering/blank-or-sourced policy, correlation n, signal/staking split, demotion-gate contract passed |
| `python3 tools/verify_2026_11_19.py --check` | A1–A8 pass: standings identities, 32-club totals, cross-page records, continuity, slate completeness, injury shape, and announced-starter evidence; see IA-F2/F3 for check semantics |
| `python3 tools/origination_desk/verify_desk.py` | 1,621 checks passed |
| `python3 tools/origination_desk/test_desk.py` | 7 tests passed |

## Decision-use summary and next steps

The repository already contains the requested dashboard, requirement/readiness registers, strategy and suggestion boards, origination/price/result schemas, injury/depth pages, and a clearly labeled review area. The key decision limitation remains the one stated across the site: a verified data/result history does not create a verified market-price feed. Keep market residuals, CLV, ROI, and any rewards unranked or blank where their required verified price inputs are absent; do not treat a mirror value as official.

Recommended order:

1. Correct the README's single-date wording to per-dataset freshness.
2. Make the official-pack `--check` mode non-mutating and test that contract.
3. Publish IA-F1 and IA-F2 on the existing Flagged for Review surface through its owner; this audit session did not edit another session's claimed generated page or flag register.
4. Continue dated, immutable official availability captures and only enable availability features after the stated chronological ablations and evidence gates pass.
