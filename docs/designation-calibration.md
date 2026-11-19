# Injury-designation reliability: data contract, not an empirical estimate

**No designation play rate is published by this change.** The repository does not contain the complete, permission-cleared multi-season, point-in-time report history and matched official game-day evidence needed to estimate one. A label such as `Questionable` is not a participation probability by itself; omission from a report is not proof of clearance, and active status is not proof of a snap.

This evaluator is a **descriptive audit tool**, not a predictive feature and not a staking input. It measures the latest recorded designation strictly before kickoff against a reviewed game-book outcome. It does not construct the required injury *surprise* feature (a dated delta), and it does not authorize use of Game Book data. The surprise signal and personnel impact still require separate chronological on/off ablations before any model use.

## Required private input files

Keep row-level evidence private until source-specific terms and permission are reviewed. Use complete histories for each player-game, including explicit pre-kickoff clears. Do not use a list containing only players whose status changed.

`reports.csv` columns:

- `season,game_id,team_id,player_id,source`
- `captured_at,kickoff,designation`

`outcomes.csv` columns:

- `season,game_id,team_id,player_id,source,game_book_status`

Timestamps must be ISO-8601 with an explicit UTC offset. `designation` must be `Questionable`, `Doubtful`, `Out`, or the explicit value `Cleared`. A blank designation is unconfirmed and rejected; do not use it to silently clear an earlier label. The `Cleared` value requires a reviewed official source that explicitly supports the change. `game_book_status` must be `played`, `active_dnp`, or `inactive`. Every row must link to a specific HTTPS URL on an NFL host. The hostname/path check only constrains URL shape: it does **not** fetch or authenticate the content, prove the transcription, establish complete coverage, or grant redistribution rights.

The recommended evidence candidates are [official NFL injury reports](https://www.nfl.com/injuries/) and the final Game Book linked from each [official game center](https://www.nfl.com/schedules/). Review the [NFL terms](https://www.nfl.com/legal/terms) and the repository's [Game Book source/reuse review](audit/official-gamebook-source-review.md) before acquiring or processing protected evidence. The exact source fields and complete coverage must be checked by an evidence reviewer; never infer starters, snaps, or participation from jersey order, depth-chart position, or absence from a page.

## Run and interpret

The command-line evaluator **requires** `--manifest evidence-review.json`; it will not emit rates from bare CSVs. The hash-bound manifest must record `complete_official_evidence: true`, `official_sources_reviewed: true`, a reviewer and offset-aware review timestamp, the covered seasons, a `team_ids_by_season` entry with 32 distinct IDs for every season, and the SHA-256 plus parsed row count for each input file (`files.reports` and `files.outcomes`). Each input row must fall within the attested season/team set and carry a specific NFL-hosted HTTPS URL. Generate file hashes only after the evidence review, for example with `sha256sum reports.csv outcomes.csv`.

The manifest is a **reviewer attestation**, not proof of completeness or source authenticity: the tool checks file hashes, row counts, declared coverage, and URL shape, but does not fetch or authenticate pages or establish permission to process or republish them. Do not create an attestation without full, source-checked official coverage. The repository currently has no such complete calibration dataset, manifest, private-store record, or terms approval; therefore no empirical play rate is reported here.

```bash
python3 tools/designation_calibration.py reports.csv outcomes.csv --manifest evidence-review.json
python3 -m unittest -v tests.test_designation_calibration
```

The evaluator picks each player's latest pre-kickoff row. A report captured at or after kickoff is ignored; a later explicit pre-kickoff `Cleared` observation clears an earlier designation, while a blank is rejected rather than interpreted. For each season and designation, output includes:

- `reported`: latest pre-kickoff player-games carrying that designation;
- `n`: those with a matched reviewed game-book status;
- `unmatched`: report rows with no outcome, **not** treated as non-plays;
- `played`, `active_dnp`, and `inactive`: matched outcome counts;
- `play_rate = played / n` and a two-sided 95% Wilson interval (null when `n = 0`).

The Wilson interval is descriptive at the player-game level and does not account for within-game/team dependence or selection bias. It is not a feature-promotion gate. Report unmatched records by team and source, document the denominator, and use game-cluster uncertainty for subsequent model comparisons. Run this diagnostic on multiple seasons only after complete official evidence is available; then compare otherwise identical models with and without the verified availability-*surprise* feature on chronological holdouts. Until those gates pass, keep the injury feature out of pricing and leaderboard decisions.

## Verification performed for this implementation

Ten synthetic unit tests cover point-in-time selection, explicit clearance, missing outcomes, status counts, conflicting kickoff and duplicate evidence, malformed identities/statuses, blank-designation rejection, hash-bound manifest gates, timezone validation, and spoofed/non-HTTPS source URLs. These tests verify evaluator mechanics only; they are not NFL observations and produce no empirical designation rate.
