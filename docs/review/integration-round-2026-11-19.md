# Integration round record — `arena/49dbdc81-x1` (2026-11-19, 22:03–23:59 UTC)

Final integration and release round. Base: `main` @ `87023d2` (PR #128's merge).
Session claim: `COORDINATION.md`, tasks FI-1..FI-5, pushed before work (rule 1).
Takeover basis: rule 10 (both prior integration claims stale — `arena/ee613dd1-x1` 06:59 UTC,
`arena/621df229-x1` 19:32 UTC "session complete").

## 1. What this round integrated

| PR | Branch | Decision | Evidence |
|---|---|---|---|
| #113 | `arena/42887cb2-x1` | **Merged** (brief row 25: dated 2026 schedule announcement beside the live schedule) | Its only conflict was the append-only `COORDINATION.md`; resolved keeping both session records. Its announcement card is mutation-tested at build time against a stored verbatim excerpt of [media.nfl.com's 2026 schedule announcement](https://media.nfl.com/football-information/2026/news/2026-nfl-schedule-announced). |
| #92 | `arena/55c364b6-x1` | **Merged** with conflict resolution (round-6 stores) | New stores kept: `data/availability_series/`, `data/fixtures/`, `data/verification/2026_11_18/`, new pages `console/availability-series.html`, `console/fixture-context.html`, `console/mind-change.html`, new builders/verifiers. Its already-absorbed content (mind-change register, `tools/verify_mind_change.py`, game-centre parser, week-aware deltas via commit `4221068`) merged byte-identically or was superseded by main's copy. |
| #91 | `arena/efb06932-x1` | **Left open** — duplication analysis recorded (flag F-37) | Its venue register / mind-change / luck-panel content is duplicated by newer main-side implementations (R7's verified venue register + `venues/index.html` + gates, the merged round-6 mind-change register, `console/luck.html`). A wholesale merge would put two competing "latest" venue stores and two mind-change tools on main. Its one clearly unique asset (the scheduled `.github/workflows/game-centre-venue-capture.yml`, which runs on CI) is named in F-37 for an owner decision. |
| #95 | `arena/8d2bacbb-x1` | **Closed as superseded** | `docs/audit/public-release-boundary.md` already on main from PR #125 lineage (`a30e9aa`, session `arena/fccb0ff1-x1`'s recorded H-95 takeover). Its branch also fails `verify` because it pre-dates the 2026-11-19 builder fixes; the merged equivalent passes. |
| #96 | `arena/3ea00c0a-x1` | **Closed as superseded** | `tools/designation_calibration.py` + `tests/test_designation_calibration.py` already on main from PR #125 lineage (`b93d491`, recorded H-96 takeover). |
| #110 | `arena/427c1843-x1` | **Closed as superseded** | The per-check measured counts (no dashes in the A-table) already on main from PR #125 lineage (`b1981f6`, recorded H-110 takeover; room page reports 6 pass / 2 review / 0 fail with measured counts). |
| #123 | `arena/41954ed5-x1` | **Left HELD** (author's own hold) | Its author holds it pending reconciliation of two conflicting 82-row brief-coverage registers (merged R8-3 `docs/review/round8-brief-coverage.tsv` vs #123's `docs/audit/brief-coverage-2026-11-19.md`). Recorded in F-37; not resolved by force here. |

No session's branch was pushed to. Individual PRs #113/#92 will be marked merged by GitHub when
their head commits reach `main` through this session's release PR.

## 2. Conflict resolutions (log, per rule 6)

- `COORDINATION.md` (#113, #92): both sides kept; the board is append-only.
- `.github/workflows/pages.yml` (#92): both step blocks kept (main's newer gates + pr92's round-6 store gates, appended additively).
- `src/console/content.py` (#92): main's newer SG-15 `decision_status` (done 2026-11-18) kept; pr92's new SG-16..SG-19 entries appended; pr92's superseded `proposed` line for SG-15 dropped. Result parses (`ast.parse`) and carries 18 questions (Q-01..Q-18) and 19 suggestions (SG-01..SG-19), asserted by the merged gates.
- `tools/build_console.py` (#92): nav combines pr92's mind-change entry and 18/19 decision counts with main's canonical decision-center link.
- `tools/verify_injuries_from_raw.py` (#92, add/add): pr92's full CLI kept (superset of main's 61-line parser, same `parse()`); patched (see §3).

## 3. Defects found and fixed during integration (all on this branch)

1. **Raw-byte injury check compared the wrong capture.** The ledger now holds Week 11 page
   captures (the live page rolled over), so pr92's `verify_injuries_from_raw.py` compared a
   Week 11 page (253 rows) against the published Week 10 table (347 rows) — 348 false mismatches.
   Fix: the comparison capture is now the newest retained capture whose printed week equals the
   published table's week column; if none, it fails loudly. `published_at_utc` preserved for the
   page builder. Result: comparison capture 2026-11-18T03:24:04Z, 1,735 cells, 0 mismatches, and
   the output now records the Week 10→Week 11 transition (+227 rows on 2026-11-19) in its
   movement section instead of failing.
2. **Availability series rebuilt from the fuller merged ledger** (19 captures, 6 distinct
   contents, 104 cell changes vs pr92's committed 15/3/32 — main's ledger gained captures after
   pr92 branched). Downgrades-in-surprise-window still 0.
3. **Feed-closure measurement regenerated** (M5 artefacts 61 → 62): pr92's new
   `tools/build_fixture_context.py` names the results feed; `lab/closure.html` re-rendered.
4. **Decision-readiness register re-measured** from the merged store (94 dated captures across
   7 datasets; R-29/R-30 "stands today" values updated by their own builders, not by hand).

## 4. Verification of the combined tree

| Check | Result |
|---|---|
| `tools/verify_data.py` | all integrity checks passed (incl. 9 starters ruled OUT in Week 10 listed) |
| `verify.yml` replay (53 committed steps + pr92 additions = 56 steps) | **55 pass, 1 fail** — the single fail is the pre-registration freshness check, which compares against a register built by CI's **shallow** checkout; proven reproducing in a depth-1 clone (the CI shape): `CHECK OK`, anchors carried forward, rule-hash comparison green. This is the documented shallow/full-clone artifact recorded by `arena/525b792a-x1`. |
| `pages.yml` replay | **24 pass, 0 fail** |
| `tools/check_links.py` | 214 files, 53,358 assertions, all links resolve |
| `scripts/verify_site.py` | 429 HTML pages; every data-table row sourced or explicitly marked |
| `tools/verify_deployed_tree.py` | 218 of 222 reachable; the same 4 pre-existing orphans reported, not failed (`live/repo-review.html`, `live/sources.html`, `live/strategy-lab.html`, `pages/executive-brief.html`) |
| `tools/audit_landing_numbers.py --check` | 10 claims, all match committed data |
| `tools/verify_2026_11_16.py --check` | CHECK OK |
| `tools/verify_console.py` | 36 pages, 3,533 data rows, 0 unsourced |
| Depth re-check inside console build | 86 slots, 0 mismatches |
| Origination & Skill Desk | reproduces, unit checks pass |

## 5. Live official-source spot checks (fetch tool, 2026-11-19 ~22:40 UTC)

- [NFL Week 10 schedule](https://www.nfl.com/schedules/2026/by-week/week-10) re-read live: all
  12 finals visible in chunk 0 match `data/evidence/2026_11_17/week10_finals.tsv` cell for cell
  (WAS 24–21 NYG; NE 10–35 DET; KC 35–13 ATL; HOU 24–27 CLE; MIN 30–10 GB; MIA 22–24 IND;
  CAR 20–17 NO; BUF 31–12 NYJ; JAX 40–23 TEN; LA 34–6 AZ; SEA 21–13 LV; SF 46–40 DAL). The
  remaining 2 finals (PIT 18–38 CIN, LAC 23–20 BAL) are re-checked by the workflow's independent
  re-transcription gate, which passes.
- [NFL standings](https://www.nfl.com/standings/division/2026/REG): records printed live
  (BUF 8-1, SF 8-1, DET 7-2, CLE 6-4) equal the committed 2026-11-14 standings snapshot plus
  the published Week 10 finals — consistent with the reconciliation gates (ΣW=ΣL, 32/32) that
  run in CI.
- Live re-reads are recorded as of their fetch time; nothing in the committed data was edited
  to match them. All committed rows keep their own dated official source links.

## 6. Irregularities published this round

- **F-37** (new, `data/flags.json`, published on the Flagged for Review page): the PR
  coordination state above — superseded/held/duplicated PRs, what is verified, what is unknown,
  and the two owner decisions that would settle it (canonical venue register; canonical
  brief-coverage register).
- Pre-existing flags F-01..F-36 remain published and unchanged.

## 7. Limits

- The sandbox shell cannot reach nfl.com (fetch tool only), so live reads above are manual
  records, not retained hashed captures.
- The pre-registration register on main is the shallow-CI build; a full-history rebuild differs
  by design (`history_scope.shallow`, `anchor_carried_forward`) and was not committed.
- `verify_2026_11_16.py`/`verify_2026_11_19.py` re-stamp `generated_at` on non-check runs; those
  rewrites were reverted, not committed, per the recorded hygiene rule.
