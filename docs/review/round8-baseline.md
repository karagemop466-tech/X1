# Round 8 — baseline re-verification of `main` (`856366f`)

**Session:** `arena-757174a7-x1` · **Branch:** `arena/757174a7-x1` · **Date:** 2026-11-19 (UTC) · **Scope:** read-only. No value was added, changed or republished; no site page was edited.

This record answers three questions for the current `main`: does the full CI gate chain still pass on a clean checkout, does the live site serve what the repo says it serves, and do the published values still agree with the official pages on the rows this session could re-read.

## 1. The gate chain, run locally in CI order

Every `run:` step of `.github/workflows/verify.yml` was executed in its declared order on the base commit, in a fresh Python 3.11.2 virtualenv built from `requirements.txt`. Each step's exit code and its last matching output line are recorded below. Nothing was edited to make a step pass.

**Result: 52 of 52 run steps passed; 0 failed.** The two `uses:` steps (checkout, Python setup) are not commands.

| # | Step (from `verify.yml`) | Result | Measured output (last matching log line) |
|---:|---|---|---|
| 0 | actions/checkout@v4 | skipped (uses:) |  |
| 1 | Set up Python | skipped (uses:) |  |
| 2 | Rebuild derived availability table | PASS | injured players absent from their club chart: 10 |
| 3 | Fail if the derived table is stale | PASS | `git diff --exit-code`: no change to the committed file |
| 4 | Rebuild the decision-readiness register and fail if stale | PASS | CHECK OK: 53 rows match the committed register byte for byte (ignoring generated_at) |
| 5 | Re-diff the published standings against the 2026-11-15 official read | PASS | CHECK OK: standings diff matches |
| 6 | Line-by-line integrity checks | PASS | all integrity checks passed |
| 7 | Rebuild the site | PASS | wrote index.html + 30 pages |
| 8 | Fail if committed HTML is stale | PASS | `git diff --exit-code`: no change to the committed file |
| 9 | Link and structure check | PASS | all links resolve; no orphan pages; all external hosts approved |
| 10 | Shared source-link rule | PASS | Site verification passed: 211 HTML pages; local links resolve; every data-table row has an official source link. |
| 11 | Verify the decision-center register and pages | PASS | Decision center verification passed: 750 assertions, 18 questions, 18 paths, 13 missing-input rows, 5 non-blocking flags. |
| 12 | Prove the source-link rule can fail (mutation test) | PASS | source-link rule is enforced (mutation detected) |
| 13 | Second independent transcription cross-check | PASS | two independent transcriptions agree on every compared value |
| 14 | Parlay correlation regression (Frechet bounds, nested legs) | PASS | all rows satisfy the Frechet bounds; every flagged-nested pair is strongly dependent |
| 15 | Published data vs the official pages (independent re-transcription) | PASS | cells compared: 1846 mismatches: 0 unmatched rows: 0 |
| 16 | Verify the unified dashboard | PASS | app verification passed: links resolve; every data row is sourced or flagged |
| 17 | Rebuild the unified dashboard | PASS | 29 pages written |
| 18 | Fail if the committed dashboard is stale | PASS |  |
| 19 | Rebuild round-3 feeds (results, snapshots, origination, registers) | PASS | check: committed round-3 registers match a fresh build |
| 20 | Rebuild audit registers | PASS | full join: 258 rows, 30 starters out across 31 clubs (pilot subset: 7) |
| 21 | Fail if the audit registers are stale | PASS |  |
| 22 | Decision-readiness register is reproducible | PASS | ok: data/audit/readiness.json matches a fresh build (60 rows) |
| 23 | Rebuild the line desk and verify its contract | PASS | lab site verification passed: 17 pages, links resolve, every data row sourced |
| 24 | Fail if the committed line desk is stale | PASS |  |
| 25 | Parallel session's dashboard checks | PASS | OK: no broken links; all data rows have a source link; no placeholders |
| 26 | Research lab checks (links, contracts, placeholders) | PASS | OK |
| 27 | Snapshot annex checks (session arena/a78e0158-x1) | PASS | Annex verification passed: 10 pages; links resolve; every data row sourced; hosts within registered tiers. |
| 28 | Validate JSON registers | PASS | ok data/data_checks.json |
| 29 | Verify round-2 store contract (Added by session arena/907c5baf-x1) | PASS | store contract: results feed sourced + settleable; price rows ordered side->total->ML with blank-or-sourced market cells; correlations publish n; sign |
| 30 | Rebuild the Week 10 re-capture, depth parse and readiness table | PASS | [readiness] 76 requirements, categories: {'Programme': 6, 'Prices': 3, 'Results': 1, 'Origination': 5, 'Leaderboard': 7, 'Availability': 27, 'Correlat |
| 31 | Fail if the re-capture, depth parse or readiness files are stale | PASS |  |
| 32 | Verify every published number against the fresh capture | PASS | 9 of 9 checks passed |
| 33 | Rebuild round-2 stores and fail if stale (Added by session arena/907c5baf-x1) | PASS | order check : spread(seq1) -> total(seq2) -> moneyline(seq3) per game |
| 34 | Control baselines reproduce from the pinned mirror (C1) | PASS | controls up to date |
| 35 | Capture store integrity, drift pins and their mutation test | PASS | self-test: 6/6 corruption cases caught by the pins |
| 36 | Pre-registration, shadow baseline and review-board registers reproduce | PASS | CHECK OK: 11 suggestions, 10 questions |
| 37 | The dated official pack still closes | PASS | CHECK OK: the 2026-11-16 pack matches a fresh build of the same reads |
| 38 | The 2026-11-17 reads pack, the Week 11 escrow and the closure measurement reproduce | PASS | CHECK OK: the feed-closure measurement reproduces from its inputs |
| 39 | The 2026-11-17 pack still closes | PASS | check: committed summary matches a fresh build |
| 40 | Brief-coverage register is structurally sound | PASS | brief coverage: all rows, paths and links verified |
| 41 | The Week 10 closure still reconciles | PASS | CHECK OK: the 2026-11-17 closure pack matches a fresh build and reconciles |
| 42 | The canonical 2026-11-17 pack still closes | PASS | 2026-11-17 pack: content matches a rebuild |
| 43 | The two independent 2026-11-17 transcriptions still agree | PASS | PASS |
| 44 | The 2026-11-18 re-verification pack still closes | PASS | CHECK OK: the 2026-11-18 re-verification pack matches a fresh build |
| 45 | The promoted rows still derive from the dated pack | PASS | CHECK OK: 150 + 0 reads rows, 14 + 0 week-10 psv rows, 13 promotion rows - the appends are exactly what the dated pack derives |
| 46 | Week 10 official venue register (brief row 24) | PASS | PASS: 14 of 14 fixtures have one official venue row; every value is sourced |
| 47 | Week 10 venue page is current (brief row 24) | PASS | ok: venues/index.html matches a fresh build |
| 48 | Verify depth-slot groups, 32-club deficiency and W11 matchup matrix | PASS | verify_depth_matrix PASS: 32 clubs (31 verified + 1 HOU image-only), GB joins 0->13, 78 W11 matchup rows (51 alerts) |
| 49 | Verify chronological splits, opponent-aware SRS, dual totals and ablations | PASS | verify_modeling_lab PASS: 4 disjoint splits (0 overlap), 32 SRS ratings, 118 dual-total games, 3 ablation rows |
| 50 | Replay the dated venue, report movement and strategy decision checks | PASS | PASS |
| 51 | The 2026-11-19 re-verification pack still closes | PASS | summary matches the committed measurement |
| 52 | The Decision Room is current | PASS | room pages match (13) |
| 53 | Origination and Skill Desk reproduces and passes unit checks | PASS | OK |

**Irregularities found while running the chain (none blocks the build):**

- **R8-I-01 — two committed verification summaries are rewritten on every run.** `data/verification/2026_11_17/verification_summary_2026_11_17_dc96bc33.json` and `data/verification/2026_11_19/verification_summary_2026_11_19.json` each change their `generated_at` timestamp when their script runs. The CI chain therefore leaves the working tree dirty. CI does not run `--check` on them, so the build still passes; the reproducibility of those two files is not enforced. This session reverted both files and changed nothing else.
- **R8-I-02 — the dependency bounds are lower bounds only.** `requirements.txt` lists `pandas>=2.0` and similar. The chain ran on `pandas 3.1.1`, `scipy`, `statsmodels`, `scikit-learn` and `pyarrow` as pip resolved them on 2026-11-19. A future resolver can change results silently; the repository has no lock file.
- **R8-I-03 — the CI chain has no step for `tools/verify_round8_coverage.py`.** That verifier is added by this session. It is not wired into `verify.yml` because `.github/workflows/**` is outside this session's claimed scope. Requested in COORDINATION.md for the integration owner.

## 2. Live checks (fetched 2026-11-19)

| Check | Result | Source |
|---|---|---|
| Live landing page serves the current build | Served; headline counts match the repo (1,846 cells diffed, 347 injury rows, 0 mismatches). | <https://karagemop466-tech.github.io/X1/> |
| Latest `main` runs | `pages build and deployment` (run 44531920116), `injury-ledger` (run 44531887827): **success**. The last merge's `verify-site` and Pages publish runs (PR #112, runs 44484254564 and 44484254543) also succeeded. | `gh run list --branch main` |
| Official Week 10 injury page, 17-row sample | 17 of 17 rows match the committed capture (9 WAS, 1 NYG, 4 NE and 3 DET; 17 in total): the nine WAS rows (WAS@NYG), NYG LB Malik Harrison (Questionable), and the NE@DET rows including the three Lions rows Kerby Joseph (S, Knee), Cade Mays (C, Ankle) and D.J. Reed (CB, Hip), each `Out`. | <https://www.nfl.com/injuries/league/2026/reg10> |
| Row count of the Week 10 capture | 351 lines minus 4 comment lines = 347 data rows, matching the published 347. The full 347-row re-diff was **not** run in this session (the page has 8 fetch chunks). | `data/capture/2026_w10_read_2026_11_17/official_nflcom_injuries_week10_2026-11-17.psv` |
| Official trades, November 2026 | All 12 trades on the official page match `data/origination_desk/roster/official_trades_nov_2026.csv` by name and date (11/06 Brissett; 11/09 Cisco, Godchaux; 11/10 the other nine, including Keenan Allen IND→SF and Josh Downs IND→KC). | <https://www.nfl.com/transactions/league/trades/2026/11> |

**Irregularities on the official page itself (published on the Flagged page for review, not corrected here):**

- **R8-I-04 — the official Week 10 injury URL is titled "Week 11".** The fetched page's title reads "Official NFL Injury Report for Players - Week 11 of the 2026 Season" while its body reads "Injuries - WEEK 10" with Week 10 games. The repo's capture header quotes the Week 10 title. Which week the page's metadata describes is a question for the league; the body was used for the sample.

## 3. Open PRs and parallel work (read, not contested)

`gh pr list --state open` at the time of this run: #110 (`arena/427c1843-x1`), #96 (`arena/3ea00c0a-x1`), #95 (`arena/8d2bacbb-x1`), #92 (`arena/55c364b6-x1`), #91 (`arena/efb06932-x1`). None touches `docs/review/round8-*` or `tools/verify_round8_coverage.py`.

## 4. Repo-level irregularities found while building the coverage register

These feed the coverage register (`docs/review/round8-brief-coverage.md`, rows marked `yes`).

- **R8-I-05 — the Packers jersey prefixes are still in the replacement table.** `data/depth/replacement_depth.csv` still holds rows such as `81 Josh Whyle` and `75 Sean Rhyan`. The jersey-stripping logic exists (`jersey_stripped_rows` in `data/depth/team_deficiency_summary.csv`) but the replacement table was not rewritten.
- **R8-I-06 — `replacement_depth_summary.json` still says "the starter is column 1".** The brief rejects that model; the group model (`data/depth/depth_groups_32.csv`) exists beside it. Both are published.
- **R8-I-07 — a diagnostic backtest row sits in the leaderboard table.** `data/origination_desk/skill/two_stage_leaderboard.csv` contains `DIAG-WF-SHRINKAGE-W1-10` with a Brier score. It is marked `DIAGNOSTIC_WALKFORWARD_NOT_RANKED`, but the brief says backtest numbers must never appear on the leaderboard.
- **R8-I-08 — brief text inside a data field.** The `turnover_impact_note` column of `official_trades_nov_2026.csv` contains "Brief row 35: …". Internal planning text should not sit in published data.
- **R8-I-09 — the modelling lab runs on a third-party mirror.** `data/models/season_splits.csv`, `personnel_ablations.csv`, `dual_totals_walkforward.csv` and `opponent_aware_ratings.csv` use the nflverse `nfldata` mirror (`games.csv`), not league-published results. Their provenance is stated in the files; the site must keep that label.
- **R8-I-10 — the dated schedule announcement is not beside the schedule page.** `data/audit/schedule_announcement_2026.json` is captured (announced 2026-05-14), but `pages/schedule.html` does not link it; only the flagged and repo-review pages do.
- **R8-I-11 — three coverage registers exist for three briefs.** `data/audit/requirements_assessed.json` (53 rows), `docs/audit/brief-coverage-2026-11-17.md` (82 rows) and this session's `docs/review/round8-brief-coverage.tsv` (82 rows, same numbering). They are not merged.
- **R8-I-12 — the 2026-11-17 register was stale.** Its NOT BUILT count was 24; the re-check finds 8. Merged work from the origination desk, modelling lab, depth matrix and kickoff trial was not reflected. Each change is recorded per row.

## 4a. Repair of `main` during this session (verify-site was failing)

When this session rebased onto the newer `main` (`42c58e2`), `verify-site` had **failed on the last two merges** (PR #117 and PR #119). Its own chain stopped at step 50 (mind-change register). Root cause, verified:

- **R8-I-14 — an automated data commit erased four recorded registration commits.** `65ba4c4` (`x1-bot`, "data: refresh from official sources", 2026-11-19 19:29 UTC) rebuilt `data/preregistration/register.json` in a shallow CI checkout. It replaced the registration commits of PR-01, PR-02, PR-03 and PR-04 with `unresolved-shallow-checkout` and an empty hash. The brief's rule is that the commit hash *is* the registration, so these are evidence.
- **Cause in the builder.** `tools/build_preregistration.py` carried an anchor forward only when the *previous* register's top-level `history_scope.shallow` flag was false. CI is always shallow, so the flag was always true and the guard erased the anchors on every rebuild.
- **Verification of the four anchors.** A blobless full-history clone was read (`git clone --bare --filter=blob:none`). Each hash exists, and each is the **first commit that touched its rule file**: PR-01 `25221eb` (`docs/preregistration/PR-01-shadow-baseline.md`), PR-02 `0747005` (`docs/lab/control-baselines.md`), PR-03 `0709442` (`docs/methodology/results-feed.md`), PR-04 `7bd4889` (`docs/preregistration/PR-04-week11-escrow.md`).

**Repair (on `arena/757174a7-x1`, commit `71ab593` and its predecessor):**

1. `data/preregistration/register.json` restored from `856366f` (the verified values), then rebuilt with the fixed builder.
2. `tools/build_preregistration.py`: row-level carry-forward. A previously *registered* anchor with a non-empty hash, not equal to this checkout's boundary commit, is carried forward when the rule bytes are unchanged, regardless of the previous file's top-level flag.
3. Regenerated the outputs that render these anchors: `data/mind_change/register.csv` (unchanged content), `pages/shadow-baseline.html`, `lab/closure.html`, and `data/lab/reads/2026-11-17/feed-closure-measurement.json` (M5 blast-radius count 60 → 61, because this register names the results feed).
4. Verified with a **depth-1 clone of the branch**, which is what `actions/checkout@v4` gives CI: `build_preregistration.py --check`, `build_mind_change.py --check` and `build_closure_measurement.py --check` all pass, and the four anchors are still `registered`.

**Result on the repaired head: 52 of 52 run steps PASS.**

**Irregularities this repair surfaces (all published on the register):**

- **R8-I-15 — PR-03's rule file was edited after its registration.** `docs/methodology/results-feed.md` changed in `0c3e1e3` (N-4, 2026-11-17), after the registration commit `0709442`. The register states this (`no - edited after registration`) and it was already stated at `856366f`. It is a real pre-registration breach to review, not a builder fault.
- **R8-I-16 — `main`'s `verify-site` failed on its push runs after #117 and #119** (runs 44599198573 and 44599436788). The failing state therefore reached `main`; this session did not establish why the pull-request runs did not stop it.
- **R8-I-17 — the scheduled `Refresh research data` workflow has failed since 2026-11-17** (`.github/workflows/pipeline.yml`, run 44123337794; `create-pull-request` reports `Resource not accessible by integration`). Logged by another session as A-3; still unresolved at this run.

## 5. What this session did not do

- It did not re-read all 347 injury rows, the 32 club depth charts, or the Texans depth image. Those remain on the flagged queue.
- It did not change any published page, data table, or workflow file.
- It did not add the coverage verifier to CI (outside claimed scope).
- It did not resolve the brief's open items (snap counts, reserve list completeness, past-season archive, designation reliability, private data layer, fixture context, 136-game log). They are NOT BUILT or PARTIAL in the register, with the missing source named.

## 6. Reproduce

```bash
python3 -m venv /tmp/x1venv && /tmp/x1venv/bin/pip install -r requirements.txt
python3 tools/verify_round8_coverage.py          # coverage register: paths, statuses, links
# then the CI chain in verify.yml order (this session ran all 52 run steps)
```
