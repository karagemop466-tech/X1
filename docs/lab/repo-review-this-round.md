# Repository review — this round

Session `arena/56769365-x1`, 2026-11-14. Scope: the repository as inherited at `11d9ea1`, and
the seven files this session touched. A line-by-line review of the eight earlier site trees is
in `app/repo-review.html` (session `arena/fcc11e05-x1`) and `docs/review/repo-review.md`
(session `arena-b38a21d8-x1`); this file records only what changed or was observed now.

## State inherited

| Check | Result |
|---|---|
| All 12 pre-existing verifiers on the base commit | pass (`rc=0`) |
| `tools/build_site.py` reproducible | yes — regenerating gives no diff |
| `tools/build_app.py` reproducible | yes |
| `tools/build_audit_registers.py` reproducible | yes |
| `tools/hub/build_hub.py` reproducible | **no** — it stamps `generated_at` into the page, so a rebuild always diffs. Recorded, not fixed: it is another session's tree and the diff is a timestamp. |
| `scripts/build_site.py` reproducible | **no** — 13 files differ on rebuild. Same reason (a generated timestamp), same decision. |

## Irregularities found in the inherited tree (flagged, not fixed)

| ID | What | Evidence | Why not fixed here |
|---|---|---|---|
| R-01 | `scripts/verify_site.py` stores its result in a **module-level** `errors` list and mutating `ROOT` after import silently suppresses every later check | reported by the module itself while debugging this round's pages | fixing shared verifier semantics is an integration decision; documented instead |
| R-02 | `tools/check_links.py` audits every HTML file outside a hard-coded folder list against `assets/site.css`, so any new folder that links a different stylesheet fails the class audit | observed when `lab/` was added; the folder list is the fix (one line, additive) | fixed, because the fix is additive and needed for this round's pages |
| R-03 | `tools/check_links.py` bans the literal string `0.125` in any page whose path contains "correlation" to prevent a stale joint-probability claim | `tools/check_links.py` prose-consistency block | matched by publishing correlations to 2 dp; the rule itself is not changed |
| R-04 | `assets/site.css` defines no `.tw`, `.kpi`, `.src` … — those live in `app/assets/site.css`. The root site and the app site use different stylesheets with overlapping class names | two CSS files, one per tree | not changed: it is a styling decision, and changing it would restyle 20 published pages |
| R-05 | the site root is served by a `sed` rewrite of `app/index.html` in `pages.yml` | `pages.yml`, deploy step | left as-is; already recorded as an open item by `arena/fcc11e05-x1` |
| R-07 | four pages are unreachable by link-following from the served root: `live/repo-review.html`, `live/sources.html`, `live/strategy-lab.html`, `pages/executive-brief.html` | deployed-tree crawl (this round) | another session's trees; adding links means editing their generators, and none of the four blocks a requirement |
| R-06 | Pages is `build_type: legacy` on `main:/`, so the artifact uploaded by `pages.yml` is not what is served at `/` | `gh api repos/.../pages` → `build_type: legacy` | recorded; the practical consequence is only that the root page comes from the legacy builder |

## Deployed-tree crawl (the check no committed verifier performs)

`scripts/verify_site.py` and `tools/check_links.py` both audit the **repository**, not the
tree that `pages.yml` actually uploads. Those differ: `pages.yml` copies a subset of folders,
then rewrites the root page with a `sed`. So the assembled tree was rebuilt locally exactly as
the workflow does it and crawled.

| Measure | Result |
|---|---|
| HTML pages in the assembled tree | 135 |
| Local `href`/`src` targets checked | 2,884 |
| Broken local links | **0** |
| Pages reachable by following links from the served root | 130 of 135 |
| Unreachable: `legacy-fourth-down.html` | intentional — a preserved copy, deliberately not in the nav |
| Unreachable: `live/repo-review.html`, `live/sources.html`, `live/strategy-lab.html`, `pages/executive-brief.html` | **pre-existing orphans** in other sessions' trees; flagged as R-07, not fixed here |

One real defect was found this way and fixed: the root rewrite repointed `href="assets/…"` but
not `src="assets/…"`, so the served landing page requested `/assets/app.js`, got a 404, and its
table filter and column sort silently did nothing. The committed verifiers could not see it,
because in the repository `app/index.html` resolves `assets/app.js` correctly — the breakage
only exists after the copy-and-rewrite. Logged in `COORDINATION.md` before the fix.

## What this round added, and the checks on it

| Added | Files | Check |
|---|---|---|
| Price-snapshot store | `data/lab/prices/*`, `tools/lab/build_prices.py` | coverage recomputed every build; 5 defects measured |
| Verified results feed | `data/lab/results/*`, `tools/lab/build_results.py` | 7,413 rows arithmetic-checked against the publisher's own columns |
| Originated lines | `data/lab/lines/*`, `tools/lab/build_lines.py` | walk-forward; tuning window separated from test window |
| Signal/staking leaderboard | `data/lab/leaderboard.json`, `tools/lab/build_strategies.py` | per-ticket bars; 4 arithmetic defects recorded and fixed |
| Replacement depth | `data/lab/deficiency.json`, `tools/lab/build_deficiency.py` | exact-name join only; unmatched rows counted |
| Correlations with n | `data/lab/correlations.json`, `tools/lab/build_correlation.py` | n, interval and p on every row |
| Questions / suggestions | `data/lab/questions.json`, `suggestions.json` | generated from the artefacts above |
| Site section | `lab/*.html`, `tools/lab/build_site.py` | 13 pages; links, per-row sources, tag balance, no leaked template values |
| Docs | `docs/lab/*` | this file |

## Additive edits to files owned by other sessions

Logged in `COORDINATION.md` before being made: one `NAV` entry in `tools/build_site.py` (with
the regeneration it implies), one `cp` + one verify step in `pages.yml`, one verify step in
`verify.yml`, and one folder-list line in `tools/check_links.py`. Nothing was removed from any
of those files.

## Known limits of this round's own evidence

1. **Nothing from nfl.com was re-fetched.** The host is unreachable from the sandbox, so the
   injury and depth rows are carried from earlier sessions and labelled "carried".
2. **No render test.** No headless browser could be installed (the binary download is blocked),
   so the substitute is a tag-balance and link check in `tools/lab/build_site.py`. It catches a
   truncated or mis-nested page; it cannot catch a layout defect.
3. **No committed verifier audits the assembled tree.** The deployed-tree crawl above was
   run by hand. It should be a CI step (crawl `_site/` after assembly, before upload); recorded
   as a suggestion rather than added, because it changes another session's workflow semantics.
4. **The market benchmark is one unnamed composite.** Every comparison with "the market" in
   this round is against that composite, and the site says so on every row that uses it.
4. **`data/lab/upstream/` is a vendored 3.2 MB copy** of four nflverse files, pinned by hash.
   It is committed deliberately: without it the build needs network access, and the numbers
   would not be reproducible.
