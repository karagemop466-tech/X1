# Week 10 venues — transcribed from the official NFL Game Centre

**Brief row 24** · session `arena/5433abad-x1` · retrieved **2026-11-18** · scope: **Week 10 only, 14 of 272 fixtures**.

Each venue is copied from the `Game Info` block (`Location` and `Stadium`) of the official NFL Game Centre page for that game, as printed. Nothing is inferred. Scores are the Game Centre finals. The verifier is `python3 tools/verify_venues_w10.py`; the machine-readable copy is `data/nfl/venues_2026_week10.csv`.

Official fixture list used to check pairings and dates: [NFL 2026 Week 10 schedule](https://www.nfl.com/schedules/2026/by-week/week-10).

## Table

| Date | Game (away @ home) | Final (away–home) | Location (as printed) | Stadium (as printed) | Schedule CSV venue note | Label check | Source |
|---|---|---|---|---|---|---|---|
| 2026-11-12 | WAS @ NYG | 24–21 | EAST RUTHERFORD, NJ | METLIFE STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/commanders-at-giants-2026-reg-10) |
| 2026-11-15 | NE @ DET | 10–35 | MUNICH | FC BAYERN MUNICH STADIUM | FC Bayern Munich Arena, Munich, Germany | differs from Game Centre label | [Game Centre](https://www.nfl.com/games/patriots-at-lions-2026-reg-10) |
| 2026-11-15 | KC @ ATL | 35–13 | ATLANTA, GA | MERCEDES-BENZ STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/chiefs-at-falcons-2026-reg-10) |
| 2026-11-15 | HOU @ CLE | 24–27 | CLEVELAND, OH | HUNTINGTON BANK FIELD | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/texans-at-browns-2026-reg-10) |
| 2026-11-15 | MIN @ GB | 30–10 | GREEN BAY, WI | LAMBEAU FIELD | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/vikings-at-packers-2026-reg-10) |
| 2026-11-15 | MIA @ IND | 22–24 | INDIANAPOLIS, IN | LUCAS OIL STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/dolphins-at-colts-2026-reg-10) |
| 2026-11-15 | CAR @ NO | 20–17 | NEW ORLEANS, LA | CAESARS SUPERDOME | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/panthers-at-saints-2026-reg-10) |
| 2026-11-15 | BUF @ NYJ | 31–12 | EAST RUTHERFORD, NJ | METLIFE STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/bills-at-jets-2026-reg-10) |
| 2026-11-15 | JAX @ TEN | 40–23 | NASHVILLE, TN | NISSAN STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/jaguars-at-titans-2026-reg-10) |
| 2026-11-15 | LA @ AZ | 34–6 | GLENDALE, AZ | STATE FARM STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/rams-at-cardinals-2026-reg-10) |
| 2026-11-15 | SEA @ LV | 21–13 | PARADISE, NV | ALLEGIANT STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/seahawks-at-raiders-2026-reg-10) |
| 2026-11-15 | SF @ DAL | 46–40 | ARLINGTON, TX | AT&T STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/49ers-at-cowboys-2026-reg-10) |
| 2026-11-15 | PIT @ CIN | 18–38 | CINCINNATI, OH | PAYCOR STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/steelers-at-bengals-2026-reg-10) |
| 2026-11-16 | LAC @ BAL | 23–20 | BALTIMORE, MD | M&T BANK STADIUM | — | blank in schedule CSV | [Game Centre](https://www.nfl.com/games/chargers-at-ravens-2026-reg-10) |

## Flagged for review

1. **Label difference, NE @ DET (Munich).** The Game Centre prints `FC BAYERN MUNICH STADIUM`; the schedule CSV prints `FC Bayern Munich Arena, Munich, Germany`. The Game Centre string is what is published here. The Game Book PDF for the same game uses a different label (see `docs/audit/official-gamebook-source-review.md`). Both are official; they are not reconciled here.
2. **Schedule CSV is incomplete for Week 10.** 13 of 14 `venue_note` cells are blank in `data/nfl/schedule_2026_week10.csv`. This session did not edit that file (it is shared, and its owner is not this session).
3. **Schedule CSV finals are incomplete.** The `result` column is filled for one game only (WAS @ NYG, 24-21). Each of the 14 official Game Centre pages shows a `Final` status and the final score (e.g. [Game Centre, Steelers @ Bengals](https://www.nfl.com/games/steelers-at-bengals-2026-reg-10): 18–38). The venue register carries the finals; the schedule file does not.
4. **Scope.** Week 10 only. The official announcement states 272 regular-season games ([NFL media announcement](https://media.nfl.com/football-information/2026/news/2026-nfl-schedule-announced)); 258 venues are not yet transcribed.
5. **Snapshot.** Game Centre pages change (for example, the injury and game-status panels). Venues do not normally change, but the retrieval date is recorded per row.

