# Source registry & verification protocol

Every published value points at one of the sources below. If a source is not on this page, a value
derived from it does not belong in a table.

---

## 1. Verification tiers

| Tier | Meaning | May populate a data table? |
|---|---|---|
| **A** | Official league page (`nfl.com`, `operations.nfl.com`, official rulebook) | Yes |
| **B** | Official club page (an NFL club property), where the club itself labels the content self-reported or unofficial | Yes, **labelled B on the row** |
| **C** | Derived by this repository's own documented join of A/B inputs | Yes, **labelled C and reproducible by script** |
| **D** | Independent secondary (news outlet, aggregator) | **No** — may only appear in a flag's corroboration column |

The build refuses a D-tier URL in a data row. That is how the rule survives contact with deadlines.

## 2. Sources actually fetched for this release (2026-11-14)

| Tier | Source | Used for | URL |
|---|---|---|---|
| A | NFL.com division standings | 32-team records, division groups, PF/PA, home/road/div/conf splits, streaks | https://www.nfl.com/standings/division/2026/REG |
| A | NFL.com conference standings | conference grouping and rank order | https://www.nfl.com/standings/conference/2026/REG |
| A | NFL.com Week 10 schedule | 14 games, kickoff times, networks, byes, final score of WAS@NYG | https://www.nfl.com/schedules/2026/REG/week/10/ |
| A | NFL.com injury report (Week 10, deep link) | 345 player rows: position, injury, practice status, game status | https://www.nfl.com/injuries/league/2026/reg10 |
| A | NFL.com injury report (index) | confirms practice-day structure and in-season mutation | https://www.nfl.com/injuries/ |
| A | NFL.com teams index | confirms the 16 NFC / 16 AFC club split | https://www.nfl.com/teams/ |
| A | NFL.com team pages (BUF, LAR) | confirms division names for the printed groups and division rank | https://www.nfl.com/teams/buffalo-bills/ · https://www.nfl.com/teams/los-angeles-rams/ |
| A | NFL.com playoff-predictions article | names all eight divisions and their member clubs | https://www.nfl.com/news/2026-nfl-playoff-predictions-picking-every-division-winner-and-wild-card-team-at-midseason |
| A | NFL.com game page | grading source for a final score | https://www.nfl.com/games/commanders-at-giants-2026-reg-10 |
| A | NFL.com player pages | per-player injury links | e.g. https://www.nfl.com/players/sam-darnold/ |
| A | NFL Football Operations rulebook (2026) | game rules; establishes that the rulebook does not settle wagering | https://operations.nfl.com/the-rules/nfl-rulebook/ |
| A | NFL Gambling Policy for NFL Personnel (PDF, 2022) | eligibility and integrity constraints on rewards/entrants | https://nflpaweb.blob.core.windows.net/website/Gambling-Policy-from-2022-League-Policies-for-Players.pdf |
| A | NFL.com news — Drew Lock to start | corroborates SEA QB replacement | https://www.nfl.com/news/drew-lock-no-injury-designation-seahawks-raiders |
| A | NFL.com news roundup — Lamar Jackson to IR | corroborates BAL QB change on 2026-11-05 | https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-thursday-nov-5 |
| A | NFL.com news — gambling policy education | league integrity/monitoring posture | https://www.nfl.com/news/nfl-increases-gambling-policy-education-integrity-monitoring-efforts-following-successful-offseason |
| B | Buffalo Bills depth chart | BUF depth order | https://www.buffalobills.com/team/depth-chart |
| B | Seattle Seahawks depth chart | SEA depth order | https://www.seahawks.com/team/depth-chart/ |
| B | Detroit Lions depth chart | DET depth order (printed "Unofficial") | https://www.detroitlions.com/team/depth-chart |
| B | Green Bay Packers depth chart | GB depth order (printed "Unofficial, Nov. 10, 2026") | https://www.packers.com/team/depth-chart |
| B | Baltimore Ravens depth chart | BAL depth order | https://www.baltimoreravens.com/team/depth-chart |
| D | ESPN Cardinals team page | **corroboration only** — used to settle the AZ 2-6 vs 3-6 discrepancy | https://www.espn.com/nfl/team/_/name/ari/arizona-cardinals |
| D | FOX Sports Cardinals standings | **corroboration only** — same discrepancy | https://www.foxsports.com/nfl/arizona-cardinals-team-standings |

## 3. Sources that do **not** exist, and the consequences

| Source we wanted | Reality | Consequence |
|---|---|---|
| League-wide official depth chart on nfl.com | Not published | No "2nd/3rd string" claim can be a Tier-A fact |
| Official snap-count feed | Not available without a licence | The snap-share fragility model is specified but uncomputable (Q-04) |
| Official historical odds | Not available without a licence | No edge, EV or CLV can be computed (Q-02) |
| Official correlation dataset | Does not exist as a product | ρ values cannot be published (Q-10) |

## 4. Re-verification procedure (how a reviewer checks a row)

1. Open the row's source link.
2. Confirm the entity and the value, in that order.
3. If the official page prints nothing, the cell must be blank. A filled cell with no printed source
   is a defect; raise it as a flag.
4. If the official page disagrees with our row, the page wins and the row is corrected with a note.
5. For Tier C rows, re-run `python3 tools/build_availability.py` and confirm the output is identical.
6. For any table, run `python3 tools/verify_data.py`; it must print `all integrity checks passed`.

## 5. Provenance rules this repository enforces

| Rule | Enforced by |
|---|---|
| Every data row links to a source | `tools/verify_data.py` asserts the URL prefix per table |
| No inferred values | Blank cells are valid; the generator never fills a blank |
| Derived rows are reproducible | `tools/build_availability.py` is deterministic and committed |
| Tier D cannot appear in a data row | documented rule + code review of the TSVs |
| Staleness is visible | every file header carries the retrieval date; pages display it |
