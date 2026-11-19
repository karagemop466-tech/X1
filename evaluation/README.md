# NFL-EVAL-01 · chronological evaluation

**Disposition:** use the locked 136-game 2026 Weeks 1–9 subset for retrospective outcomes-only research. It is a corpus definition, not a strategy registration and not a claim of prospective skill. No scoring run was made for this change. 2027 is a candidate final holdout only, not an assertion of a published fixture list or an active strategy.

## Evidence and method

- `protocol.json` records mutually exclusive regular-season windows. A strategy-specific protocol must define features and scoring, ties/pushes, prescheduled update policy, benchmark, thresholds, and timestamped forecasts before the first eligible kickoff. Use training for fitting, validation for selection, and final holdout for one locked evaluation. Do not reuse the final holdout for tuning or place retrospective metrics on the leaderboard.
- `evidence-lock.json` pins the exact bytes of the protocol and nine retained 2026-11-14 NFL schedule extracts and their corresponding structured transcriptions. The Git commit records this lock; it cannot make an already-played game prospective. Correct a source by publishing a new version, not by silently repinning this one.
- `tools/evaluation/build.py` verifies all 136 game URLs, weeks, dates, teams and scores between the retained NFL schedule anchors and the structured official schedule transcriptions. The results are keyed by Game Center URL and compare only the repository's explicit Arizona/Rams code aliases (`ARI`/`AZ`, `LAR`/`LA`). The separate `tools/verify_results_feed.py` checks the 137-row dated view against 32 teams' same-date official standings. These offline checks trace back to retained NFL readings and do not treat the transcriptions as independent fresh NFL reads.
- This session also re-read the [official Week 9 slate](https://www.nfl.com/schedules/2026/by-week/week-9) and [Week 1 Patriots–Seahawks Game Center](https://www.nfl.com/games/patriots-at-seahawks-2026-reg-1). Each public weekly row links to the relevant NFL slate, which links to each game. The [NFL Football Operations scheduling reference](https://operations.nfl.com/calendar-events/nfl-schedule/making-the-schedule) explains the regular-season format, not our split or the 2027 fixture list.
- The 136 outcome rows exclude the Week 10 Thursday game in the 137-row dated view and all other Week 10 finals in the 150-row closure view. The older brief audit also calls the shadow sample 117; the current `data/shadow/games_scored.csv` contains 118 distinct games (including one tie), covering Weeks 3–10. It is not the corpus used here.
- No official match-level verification was added for 2019–2025. [NFL historical standings](https://www.nfl.com/standings/league/2025/REG) are not a game-by-game result feed. Do not treat a mirror agreement check as authorization or verification of a game.
- No price, ROI, CLV or betting result is generated. See the existing [N-4 price policy](../docs/methodology/price-snapshots.md#the-price-data-policy-decision-n-4-2026-11-17). No row-level input was added or republished; only the [derived HTML](../pages/evaluation.html) is linked from the dashboard.

## Checks

```sh
python3 tools/evaluation/build.py
python3 -W ignore::ResourceWarning -m unittest discover -s tools/evaluation -p 'test_*.py'
```

`--write-page` refreshes only the deterministic HTML; `load_corpus(load_protocol())` is the verified label loader for future retrospective experiments. It does not provide point-in-time features or an executable trading strategy.
