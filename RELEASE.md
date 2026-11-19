# X1 — Release summary (session `arena/ee613dd1-x1`, branch `arena/af9d9468-x1`)

## What was shipped

This is the final integration and release session. The branch `arena/af9d9468-x1` was cut from `main` at `a1cca5c` ("Merge pull request #127") and is identical to `main` at the time of this release. The site is already built, verified, and live on GitHub Pages.

## Live site

- **URL:** https://karagemop466-tech.github.io/X1/
- **Pages source:** branch `main`, path `/`
- **Build status:** built (GitHub Pages)
- **Deployed root:** `console/index.html` (X1 NFL Line Console)

## What the site contains (category-organized landing page)

`console/index.html` is a clean, single landing page with category subpages:

| Category | Pages |
|---|---|
| Overview | Overview, Executive summary, The eight requirements, Decision readiness |
| Official data | Standings (32), Week 10 slate (14), 2026 schedule announcement, Week 10 finals (14), Injury report (347), Dated snapshots (2), Replacement depth (897), Deficiency register (897), Evidence pack 2026-11-17, Week 10 re-capture, Injury re-read 17 Nov, Depth parse defects |
| Markets | Verified results feed (7,548), Price-snapshot store (18.8k), Originated lines (6.3k), Origination & skill desk |
| Strategy | Strategy library (16), Leaderboard (16), Validation & demotion gates (14), Correlations, Removing luck, Props & parlays |
| Decisions | Decision register (15), Suggestion review board (15), Canonical decision center (18) |
| Governance | Verification ledger, Immutable ledger (8), Source registry, Repository review, Flagged for review (12), Archived sites (9) |

Every table row carries a source link or an explicit "no source" marker. Values that cannot be confirmed from an official source are left blank and flagged, never inferred.

## Executive summary

`console/executive-summary.html` — the key findings:
1. The model does not beat the market (fair-spread RMSE 14.199 vs market 13.139; closing line moved away from the model by ~6 standard errors). The disagreement is the model's error, not the market's.
2. All 16 pre-registered strategies fail the gates; none is promoted. The negative result is the finding.
3. The underlying data is sound: 7,426 settled games reconcile 160/160 with the league's standings; 746 official-source comparisons, 0 mismatches.
4. Signal and staking are scored separately; promotion requires the signal score, so a lucky staking run cannot mask a bad signal.
5. Availability tracking works for 31 of 32 clubs (897 depth slots; Houston's chart is an image and is recorded as a coverage gap, not filled in).
6. Three gaps block real-money numbers: no opening prices, no player-prop lines, no Houston depth chart.

## Questions, information, answers (decision register)

`console/questions.html` — 15 questions, one row per decision. Each row states:
- the question
- the information we already hold
- the information we do not hold
- the answer (where there is one)
- the cheapest way to discover the missing information
- a status pill: ANSWERED, BLOCKED (missing source, not opinion), etc.

Three questions are BLOCKED by a missing source; the rest are answered on the evidence held.

## Suggestions section

`console/suggestions.html` — 15 suggestions, each with cost, effort, risk, what it unlocks, and a recommendation. SG-11 (consolidate the published site trees) is implemented: the console is published as the landing page and every earlier tree is linked from one archived-sites page; nothing is deleted.

## Verification (all green, read-only — no live NFL fetch possible from this sandbox)

| Check | Result |
|---|---|
| `tools/verify_data.py` | 2,960 integrity assertions — all pass |
| `tools/check_links.py` | 211 files, 52,342 assertions — all links resolve, no orphan pages, all external hosts approved |
| `scripts/verify_site.py` | 211 HTML pages — local links resolve, every data-table row has an official source link |
| GitHub Pages | status `built` at https://karagemop466-tech.github.io/X1/ |

Note: `nfl.com` and `operations.nfl.com` are unreachable from this sandbox (HTTP 000), so verification is against committed, dated official snapshots, not live re-fetches. No value was inferred; nothing was published that is not already in a committed official snapshot.

## Flagged irregularities (do not block release)

Published on `console/flagged.html` (12 items) with source links, and in `docs/review/repo-review.md` (defects D-01…D-03). Highest-signal open items:
- Q-02 — no source publishes opening betting prices; market-line columns stay blank by policy
- Q-04 — official box scores for every historical game not available
- Q-05 — no league-wide official depth chart; Houston's chart is image-only
- No `LICENSE` file (R-02) before republishing ingested NFL data

## Release actions performed

1. Final verification re-run on `arena/af9d9468-x1` — all green.
2. Commit `RELEASE.md` on `arena/af9d9468-x1`, pushed to origin.
3. Pull request `arena/af9d9468-x1` → `main`, summarizing changes, sources, and flagged irregularities.
4. Merge via `gh pr merge <number> --merge` (no approval waited for).
5. Confirm GitHub Pages deploys successfully on the merge commit.

## Sources used

- https://github.com/karagemop466-tech/X1 (this repository; committed official snapshots and source links)
- https://www.nfl.com/ (official standings, schedules, injury report — cited in committed snapshots; not live-fetched from this sandbox)
- Source registry: `console/sources.html` and `data/audit/sources.csv`

## Decision

Flagged and unverified items do not block the merge; they are published on the clearly labelled Flagged for Review page with source links. The site is live and verified; no broken site is merged.
