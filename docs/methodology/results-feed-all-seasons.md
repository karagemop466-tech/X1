# Verified results feed

**Requirement:** "Add a verified results feed so backtests and ROI can be computed at all."
*(Owner's brief, T11, session `arena-52aabfa8-x1`.)*

**Machine-readable outputs:** `data/results/verified_results.csv` (2,232 rows, seasons
2019–2026) and `data/results/results_feed_meta.json` (sources, checks, limitations).
**Builder:** `python3 tools/build_results_feed_all_seasons.py` — deterministic, offline, exits non-zero
if any cross-check fails.

---

## 1. Why this exists

Every ROI figure, backtest and skill test settles against a final score. Before this feed the
scores lived implicitly inside a third-party mirror file (`games.csv`) with no verification
tier attached, so nothing could say which results were confirmed against an official page.
The feed makes the tier explicit **on every row**.

## 2. Verification tiers (per row)

| `verification` | Meaning | Count |
|---|---|---|
| `official_verified` | The score was printed by the committed transcription of <https://www.nfl.com/schedules/2026/by-week/week-10> (fetched 2026-11-14) **and** the mirror carries the same score. | 1 |
| `scheduled_official` | The same official snapshot confirms the game had not been played at fetch time. Score cells are blank because no score exists — never because it was unreadable. | 13 |
| `mirror_only` | The value exists only in the fingerprinted third-party mirror (`nflverse/nfldata`, sha256 in `data/raw_manifest.json`). Flagged; never labelled official. | 2,218 |

A row with `official_source_url` set is a row you can click through to the page the value was
read from. Historical finals carry no committed official page in this repository, so they are
`mirror_only` — usable for backtests, labelled not official (flag **F-11**).

## 3. Cross-checks (all must pass or the builder exits 1)

| ID | Check | Result |
|---|---|---|
| C1 | Official Week 10 FINAL score == mirror score (WAS 24, NYG 21) | pass |
| C2 | Official "Scheduled" status == mirror status for the other 13 Week 10 games | pass |
| C3 | Mirror internal arithmetic: `away+home == total` and `home-away == result` on every final row (2,097 rows) | pass |
| C4 | 2026 W/L/T recomputed from this feed vs the official standings snapshot | pass, with one known difference class |

**C4's known difference (flag F-12).** The official standings snapshot as fetched on
2026-11-14 still reads WAS 3-5-1 and NYG 5-3-1 — the records **before** the Thursday Night
game — while the same site's schedule page already prints "Commanders 24, Giants 21, FINAL".
The feed (and the mirror standings) carry the post-game record. Both standings sources agree
with each other and both predate the result; the difference is freshness, not contradiction,
and it is recorded rather than smoothed over. This is also the concrete example of why two
sources agreeing is not the same as both being current.

## 4. Joining to a bet (how ROI is computed)

Settlement is a join on `game_id`:

```
result for a bet on side S with recorded line L =
    W if (S covers L)   — using away_score / home_score from the feed row
    P if exactly L
    L otherwise
```

Only rows with `status=final` settle. Scheduled rows contribute nothing. No row is invented:
a game that has not been played has blank score cells by construction.

## 5. Team-code note

The official pages print **AZ**; the nflverse mirror prints **ARI**. Every other club code is
identical across the three committed snapshots (diffed). The join maps only these two
spellings (`TEAM_CODE_MAP` in the builder); each source keeps its own spelling in its own
file.

## 6. What this feed does *not* close

- **Q-04 (official box scores for every game)** stays open. This feed verifies what a
  committed official page printed; for 2,218 rows no such page is committed yet. The per-row
  `verification` column is exactly the map of that gap.
- The feed carries no betting prices — that is the price-snapshot store's job
  (`docs/methodology/price-history.md`), and no official source publishes prices (F-06).
