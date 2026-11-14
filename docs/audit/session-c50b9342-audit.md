# Audit — session `arena/c50b9342-x1` (2026-11-14)

Independent line-by-line audit of the repository as found at `main` commit
`0699aff1c88a4d5970893ed334274f0b44145d19` ("ci: diagnostics pipeline"), plus repair of a
broken CI check. This session is a **verification & repair session**: no published NFL value
was changed, because every value re-checked against its official source matched exactly.

---

## 1. Findings

### F-A1 (defect, fixed) — `verify-site` failing on `main` since PR #20

- Evidence: Actions runs [`43558636038`](https://github.com/karagemop466-tech/X1/actions/runs/43558636038),
  [`43558647106`](https://github.com/karagemop466-tech/X1/actions/runs/43558647106),
  [`43558937848`](https://github.com/karagemop466-tech/X1/actions/runs/43558937848),
  [`43558987979`](https://github.com/karagemop466-tech/X1/actions/runs/43558987979),
  [`43559100989`](https://github.com/karagemop466-tech/X1/actions/runs/43559100989) —
  step **"Link and structure check"** (`tools/check_links.py`) failed on every `verify-site`
  run after PR #20 merged; the Pages deploy (a different workflow) kept succeeding, so the
  failure was easy to miss.
- Root cause (three classes, all in `tools/check_links.py`, none in the `live/` content):
  1. `live/*.html` were audited against `assets/site.css` (the wrong stylesheet — they load
     `assets/x1-live/site.css`), producing ~80 false "class used but defined nowhere" errors.
  2. `live/` pages are JS-rendered; `href="${r._source_url}"` template literals inside
     `<script>` blocks were scanned as static links → false "internal link resolves" errors.
  3. The `live/` tree was not reachable from `index.html` → false "orphan page" errors, and
     the `live/` pages do not print the snapshot date in static markup (the date lives in
     `data/pipeline/*.json`, which `scripts/pipeline/verify_site.py` validates row by row).
- Fix (additive, follows the existing per-tree contract pattern already used for
  `dashboard/` and `research/`): `live/` scoped to its own stylesheet + JS-hook root;
  `<script>` blocks stripped before the href/class scans; `live/index.html` admitted as an
  alternate root; per-page contract for `live/` limited to "links its stylesheet" (its full
  contract remains `scripts/pipeline/verify_site.py`).
- Result: `python3 tools/check_links.py` now passes with **82 files / 9,879 assertions / 0 failures**.
- Note: PR #20's session ran `scripts/verify_site.py` (the pages.yml checker) and reported it
  passing — which was true — but `verify.yml` runs `tools/check_links.py`, a different
  checker. Both now pass.

### F-A2 (gap, fixed) — the `live/` section was unreachable from the main site's navigation

PR #20 logged a request ("please add a navigation card linking to `live/index.html`") that no
later session actioned. The nav entry **"Live pipeline"** was added to the NAV list in
`tools/build_site.py` and the site regenerated (+1 nav line on each of the 15 generated
pages, nothing else). No live-pipeline file was modified.

### F-A3 (observation, no action) — duplicated constant definitions in `tools/check_links.py`

`RESEARCH_APPROVED` and `ANNEX_APPROVED` were each defined twice (pre-existing, harmless —
second definition wins, sets are identical). Left untouched to keep this session's diff
minimal; flagged here for the owning session.

## 2. Independent re-verification (this session, sources fetched 2026-11-14)

| Dataset | Rows compared | Method | Result |
|---|---|---|---|
| Standings (live pipeline, `data/pipeline/standings.json`) | 32/32 | W, L, T, PF, PA transcribed from <https://www.nfl.com/standings/league/2026/REG> (fetched this session) and diffed programmatically | **0 mismatches** |
| Standings (annex, `data/nfl/teams_standings_2026_w10.csv`) | 32/32 | same official values | **0 mismatches** |
| League arithmetic | 32 clubs | ΣPF = ΣPA on the official numbers themselves | **6291 = 6291** ✓ |
| Injury report (`data/pipeline/injuries.json`) | 44/44 (WAS 9, NYG 11, NE 15, DET 9) | rows transcribed from <https://www.nfl.com/injuries/> (Week 10 2026, fetched this session) and diffed | **0 mismatches** (2 apparent diffs were transcription artifacts on the auditor's side: page prints "Chig Okonkwo" and "Carlton Davis III"; repo matches the page) |
| Team stats, scoring (`data/pipeline/team_stats.json`) | SF, BUF rows | <https://www.nfl.com/stats/team-stats/offense/scoring/2026/reg/all> fetched this session; SF = 12/17/31/1, field names carried in the dataset | **exact match, value for value** |
| CI verification chain | 14 steps | all steps of `.github/workflows/verify.yml` run locally in CI order | **all pass** |
| Live-pipeline checkers | 2 | `scripts/pipeline/verify_data.py` (4,579 rows, 0 without official source), `scripts/pipeline/verify_site.py` | **both pass** |
| Scheduled collector health | — | `_ci/pipeline.log` (exit=0, club registry 32/32), `_ci/commit.log` (push succeeded) | **healthy** |

## 3. Irregularities for review (no blocking issues found)

- **F-A1/F-A2 above** are the only defects found; both fixed by this session.
- Existing published flags **F-01…F-07** (`live/flagged.html`) and dashboard flags
  (F-08, etc., `pages/flagged.html`) were reviewed and remain correctly labelled; nothing
  was reclassified.
- Standing data limitations unchanged and honestly published: no official odds feed (no
  prices in the dashboard tier), HOU depth chart unparsable (31/32 clubs), club depth charts
  self-reported ("unofficial" per packers.com), Week-10 standings page prints no header row
  (columns positional, arithmetic-validated).

## 4. Commands to reproduce this audit

```bash
python3 tools/build_availability.py && git diff --exit-code -- data/nfl/availability_derived.tsv
python3 tools/verify_data.py
python3 tools/build_site.py && git diff --exit-code -- index.html pages
python3 tools/check_links.py
python3 scripts/verify_site.py
python3 tools/test_source_rule.py
python3 tools/cross_check.py
python3 scripts/verify_parlay.py
python3 scripts/check_site.py
python3 scripts/verify_research_site.py
python3 scripts/verify_site_annex.py
python3 scripts/pipeline/verify_data.py
python3 scripts/pipeline/verify_site.py
```
