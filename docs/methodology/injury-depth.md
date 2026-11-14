# Methodology — injury & depth-deficiency tracking (T4)

The system must know when defenses (or offenses) are running their 2nd/3rd/4th-string players
because starters are out — and quantify what that does to a game.

## What we have (verified, official)

- **Official weekly injury report** — NFL.com, Week 10, 2026: 345 player rows across the
  28 playing teams (`data/injuries/injuries_2026_week10.csv`), each row with the player-page
  URL shown on the report, practice status, and game status exactly as published.
- **Official news context** — from the NFL.com injury-report news rail (all linked on the site):
  Lamar Jackson on IR (6–10 weeks, right thumb); Drew Lock to start for SEA; Deshaun Watson to
  start for CLE; Carson Beck to start for ARI; Malik Willis to IR with Kyle McCord in line for
  his first start; Puka Nacua to IR (toe/MCL/PCL); Josh Jacobs finger surgery, timeline TBD;
  Garrett Wilson in concussion protocol; trades (Amani Hooker → BUF, Daiyan Henley → DEN).
- **QB starter map** — `data/injuries/qb_map_2026_week10.csv`: expected starter per team with
  source and conflicts (MIA/ARI resolved toward the most recent NFL.com news; BAL unresolved
  until Monday inactives).

## What we can compute today

From the Week 10 report alone, per team and position group (QB/RB/WR/TE/OL/DL/LB/DB):
- count of players with game status Out / Doubtful / Questionable,
- count of Did-Not-Participate and Limited practice rows,
- position-group "load flags" (e.g., GB: 17 players listed; MIN: QB1 Kyler Murray OUT).

## What is missing for true depth-chart deficiency scoring (and how to get it)

| Missing input | Why it matters | Discovery action (suggestion) |
|---|---|---|
| Official depth charts (starter → 2nd/3rd string) | "2nd-string CB starting" is the actual signal; a game-status row alone doesn't say who steps in | Team PR departments publish weekly depth charts; collect one-time archive from all 32 club sites; store under `data/depth/` with per-row club-site links |
| Historical injury-report archive | To *validate* any injury signal you need seasons of reports joined to results | Scrape/archive NFL.com weekly reports going back (they exist per week, e.g. Week 9: https://www.nfl.com/news/nfl-week-9-injury-report-2026-season); join to nflverse results |
| Snap counts (who actually played) | Converts "backup started" into fact | Official NFL GSIS gamebooks (operations.nfl.com) / Next Gen Stats; flagged as not reachable from this sandbox |
| Player props results feed | For prop-combo strategies and their correlations | Licensed odds/stats provider (Q6) — none reachable here |

## Deficiency score (design, pending the missing inputs)

For each team-game: `deficiency = Σ (backup_steps × position_weight × availability)` where
backup_steps ∈ {1,2,3,4} is how far down the depth chart the replacement is, position_weight
reflects positional value (QB highest, then OT/CB1/EDGE/DT1/LB1...), availability = snap-share
expectation. Until depth data exists, the site publishes **position-group load flags** only —
clearly labeled as a proxy, never as a depth score.

## Rules encoded now

1. A player with **no game status** is never assumed out (F10).
2. DNP-limited with no status is "monitor"; final status = official inactives ~90 min before kickoff.
3. Resting-player designations ("not injury related - resting player") are treated as coaching
   decisions, not injuries (JAX Bates/Davis rows).
4. Every derived claim links the underlying report rows.
