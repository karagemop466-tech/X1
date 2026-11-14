# Repo review — line by line (T1)

Reviewed by session `arena-a78e0158-x1` on **2026-11-14 (UTC)**, per the owner's instruction to
work line by line, verify from official sources, and flag irregularities.

## State of the repository at review time

Commit `dab199c` ("Initial commit") contained exactly one file:

| File | Contents | Finding |
|---|---|---|
| `README.md` | 1 line: `# X1` | Stub only. No description, no data, no code, no license, no CI, no .gitignore, no GitHub Pages configuration. |

There was no prior data, no prior analysis, and no prior code to verify. Everything in this
repository beyond that stub was produced in this session and is verifiable through the sources
linked on every table row (see `docs/sources/sources.md`).

## Irregularities found and flagged

Each item below is also published on the site's **Flagged for Review** page with source links.

| # | Irregularity | Where seen | Status |
|---|---|---|---|
| F1 | Myles Garrett listed on the **Rams'** official Week 10 injury report (LB, resting). A trade path is not present in the nflverse trade log — single-source. | NFL.com Week 10 injury report | flagged — verify via Rams official roster |
| F2 | **Aaron Donald** listed on the Rams' Week 10 injury report (DT, DNP, no game status). He publicly retired in March 2024; either he returned in 2026 or the listing is a data error. | NFL.com Week 10 injury report | flagged — verify via Rams official roster |
| F3 | Multiple star players appear on new teams with the injury report as the only in-repo source: M. Harrison Jr. (HOU), M. Evans (SF, OUT Achilles), D. Lawrence (CIN), Q. Nelson (SEA, OUT), J. Porter Jr. (DAL), A.J. Brown (NE). | NFL.com Week 10 injury report | flagged — corroborate with team pages before modeling |
| F4 | **BAL quarterback conflict:** nflverse games.csv lists Tyler Huntley as Week 10 starter; an NFL.com news headline (Nov 5) reported Huntley out for the season (turf toe); no Ravens QB appears on the official Week 10 report. Lamar Jackson (thumb) is on IR 6–10 weeks. | nflverse games.csv vs NFL.com news | **unresolved** — resolve at Monday inactives (~7:15 PM ET) |
| F5 | **MIA quarterback conflict:** nflverse lists Malik Willis as Week 10 starter; NFL.com news (Nov 13) says Willis went on IR and Kyle McCord is in line for his first start. | nflverse games.csv vs NFL.com news | resolved toward McCord (most recent official), confirm at inactives |
| F6 | **ARI quarterback conflict:** nflverse lists Gardner Minshew; NFL.com news (Nov 11) says Carson Beck starts and Jacoby Brissett was benched Week 8. | nflverse games.csv vs NFL.com news | resolved toward Beck, confirm at inactives |
| F7 | Daiyan Henley appears on the **Chargers** Week 10 report even though NFL.com news (Nov 10) says Denver traded for him — explained by DEN being on bye (no bye-week report exists); verify the transaction officially before using him in any model. | NFL.com injury report + news rail | flagged |
| F8 | nflverse `rosters.csv` is **stale (ends 2019)** — official 2026 depth charts cannot be derived from it. | data/raw/nflverse/README.md | flagged — blocks automated depth analysis (see open questions Q3) |
| F9 | nflverse `closing_lines.csv` is **stale (2006–2018)**; per-game market lines in `games.csv` (2019+) are used instead. `win_totals.csv` ends 2020. | data/raw/nflverse/README.md | flagged — documented limitation |
| F10 | Several players show "Did Not Participate In Practice" with **no game status** (e.g., WAS Burks, BUF Bernard/Oliver, LAR Donald/Nacua/Fiske). Missing status ≠ availability; do not treat as out without the final injury report/inactives. | NFL.com Week 10 injury report | flagged — rule for all modeling |
| F11 | NFL.com displays the player as "Jacob Hummel" while the player URL slug is `jake-hummel` — trivial display inconsistency, recorded as displayed. | NFL.com Week 10 injury report | noted |
| F12 | The 2026 season opened on a **Wednesday** (Sept 9, NE@SEA) — unusual but confirmed by NBC Sports and nflverse. The Melbourne game (SF@LA) streamed on Netflix per Yahoo/NBC reporting. | NBC Sports, Yahoo Sports, nflverse games.csv | verified, noted for awareness |

## Verification performed

- All 32 standings rows recomputed from nflverse `games.csv` (137 played games) and compared
  cell-by-cell to NFL.com: **32/32 exact match** on W-L-T, PF, PA; wins (136) = losses (136);
  PF (6,291) = PA (6,291).
- Week 10 slate (14 games + byes CHI/DEN/PHI/TB) confirmed on NFL.com and re-confirmed from
  nflverse `games.csv`.
- International slate (9 games) confirmed on operations.nfl.com and cross-checked to nflverse
  `location = Neutral` rows — **9/9 match** (dates/teams).
- nflverse `spread_line` sign convention verified empirically against moneylines on 5,228
  games (99.4% agreement): it is the **away team's spread**.
- Injury report (345 rows) transcribed from the official NFL.com Week 10 report; every row
  carries the player-page URL shown on the report.
