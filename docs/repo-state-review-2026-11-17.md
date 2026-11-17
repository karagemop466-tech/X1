# Repository review — 2026-11-17

## Executive summary

The repository already contains a broad decision dashboard, not just a prototype: requirements/readiness pages, a suggestions and open-questions board, availability and line-origination views, validation and leaderboard pages, and a flagged-for-review page. I reran the repository's site and data checks on 2026-11-17 UTC. They pass. This establishes internal consistency and link integrity; it does **not** independently prove that each underlying NFL transcription is correct or that the model has prospective betting skill.

## Verification performed

| Check | Result | Interpretation |
|---|---|---|
| `python3 scripts/verify_site.py` | Passed; 168 HTML pages; local links resolve; every data-table row has an official source link | Site-level structural check, not a fresh external-source audit |
| `python3 tools/check_links.py` | Passed; 168 files, 44,192 assertions; links resolve, no orphan pages, external hosts approved | Internal/link policy check |
| `python3 scripts/verify_data.py` | Passed; 345 injury rows across 14 games; hard checks passed | Dataset invariants pass; does not validate each value against a live NFL page |

## Decision-ready versus blocked

| Area | Current evidence | What remains before a decision is reasonable | Official review source |
|---|---|---|---|
| Schedule and standings | The site publishes source-linked tables and structural checks pass | Refresh and date-stamp a source-to-row comparison before using current-week values | [NFL schedule](https://www.nfl.com/schedules/); [NFL standings](https://www.nfl.com/standings/) |
| Injury / availability | A 345-row dataset passes internal checks; the site has availability and snapshot surfaces | Verify each row against dated official report captures; join inactive evidence and actual snap participation before treating replacement depth as known | [NFL injuries](https://www.nfl.com/injuries/); [NFL Game Center](https://www.nfl.com/scores/) |
| Market prices | Price snapshots and origination views exist in the repo | A declared price-data policy, source permission/terms review, and complete immutable opening/closing captures are prerequisites to price-based claims | No official NFL source: market prices are operator data and must be sourced/permissioned independently |
| Model skill | Shadow-baseline and validation artifacts exist | Keep prospective, frozen forecasts; require chronological holdouts, benchmark-relative proper scores, uncertainty, control baselines, and a published demotion rule before rewards | No official NFL source: these are methodological requirements, not league facts |
| Correlations / combos | Correlation and parlay validation surfaces exist | Publish only official-source observations with sample size and uncertainty; do not rank a combo without a directly validated joint probability and explicit push/void treatment | Official result inputs: [NFL Game Center](https://www.nfl.com/scores/) |

## Suggestions for the review board

1. Treat the live site's requirement/readiness register as an evidence ledger, not a claim that all requirements are complete. Preserve explicit blocked/unverified states.
2. Before publishing any price-based backtest, resolve market-data source, capture timing, retention, permitted use, and opening/closing definition in one versioned policy.
3. Gate injury features on point-in-time availability evidence. A report designation alone does not establish who played, how many snaps they took, or which depth-chart slot they occupied.
4. Keep the leaderboard in shadow mode until frozen forecasts have a sufficiently large, prospective, chronological sample and beat named controls with uncertainty bounds.
5. Keep singles, game parlays, same-game parlays, and prop combinations in separate divisions; combos remain ineligible absent validated joint probabilities and operator settlement rules.
6. Make the review queue's first action evidence acquisition (dated official source, raw/canonical hash, capture time, conflict status), not hand-entering an unknown value.

## Irregularities / limitations

- The reported checks are repository commands and were run locally; they do not certify every displayed value against a fresh official source.
- A URL resolving is not evidence that a page is immutable, that an archived copy existed at forecast time, or that the source permits republication.
- Any unconfirmed value should remain blank and flagged rather than imputed. The official NFL source links above are starting points for review, not per-row citations.
- No new NFL statistics or performance claims are introduced in this review.
