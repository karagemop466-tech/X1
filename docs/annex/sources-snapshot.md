# Source registry & verification protocol (T2)

Rule of the project: **every value on the site and in `data/` carries a source link. If a value
cannot be confirmed from an official source, it is left blank and flagged — never inferred.**

## Source tiers

| Tier | Meaning | Sources |
|---|---|---|
| **Official** | Published by the NFL or its clubs | nfl.com (standings, schedules, injury reports, news), operations.nfl.com, team sites, SoFi Stadium host-committee release |
| **Trusted-secondary** | Well-established independent compilers built from official feeds | nflverse/nfldata (GitHub, MIT license), NBC Sports, Yahoo Sports, The Athletic, Pro Football Hall of Fame |
| **Market** | Bookmaker lines — benchmarks only, never treated as truth | market spread/total/moneyline columns inside nflverse `games.csv` |

## Registry

| Source | URL | Used for | Tier | Notes |
|---|---|---|---|---|
| NFL.com standings | https://www.nfl.com/standings/division/2026/REG | 2026 records, divisions, ordering | Official | snapshot 2026-11-14; includes W10 Thursday game |
| NFL.com standings (league view) | https://www.nfl.com/standings/league/2026/REG | PF/PA/net pts, home/road/div/conf splits | Official | same snapshot |
| NFL.com Week 10 schedule | https://www.nfl.com/schedules/2026/REG10/ | kickoff times, TV, byes, venues, flex rules | Official | all 14 games + 4 byes verified |
| NFL.com injury report | https://www.nfl.com/injuries/ | Week 10 injury report (345 rows) | Official | fetched in full (8 chunks); player-page links captured per row |
| NFL Operations international games | https://operations.nfl.com/programs-initiatives/international-growth/nfl-international-games | 2026 international slate (9 games) | Official | venues + kickoff times |
| NFL.com Week 11 schedule change | https://www.nfl.com/news/week-11-schedule-change | flexible-scheduling evidence (Mexico City) | Official | dated Nov 9, 2026 |
| SoFi Stadium news release | https://www.sofistadium.com/news/detail/los-angeles-region-to-host-super-bowl-lxi-in-2027-welcoming-the-nfls-biggest-stage-for-the-second-time-this-decade-to-sofi-stadium | Super Bowl LXI date/venue | Official | Feb 14, 2027, Inglewood CA |
| NBC Sports kickoff preview | https://www.nbcsports.com/nfl/news/how-to-watch-new-england-patriots-seattle-seahawks-nfl-opener-live-stream-preview-nbc-peacock-wednesday | Wednesday opener Sept 9, 2026; defending champion SEA | Trusted-secondary | corroborated by nflverse dates |
| NFL.com injury-report news rail | https://www.nfl.com/injuries/ (news section) | Drew Lock start; Lamar Jackson IR 6–10 wks; Watson start; Beck start; Willis IR/McCord; trades (Hooker, Henley); Nacua IR; Jacobs surgery | Official | headlines dated Nov 5–13, 2026 |
| nflverse/nfldata | https://github.com/nflverse/nfldata | historical results 1999–2026, market lines, trades | Trusted-secondary (MIT) | fetched via GitHub API 2026-11-14; local copies in `data/raw/nflverse/` |

## Verification protocol (how rows are marked)

1. A row is `verified` only when the value was read from an **Official** or **Trusted-secondary**
   source and, where possible, cross-checked against an independent second source.
2. Cross-checks performed this session: standings 32/32 (NFL.com vs recomputed nflverse results),
   Week 10 schedule 14/14, international 9/9, spread-line convention 5197/5228 games.
3. Anything single-sourced and surprising → **Flagged for Review** (site page + `docs/review/repo-review.md`).
4. Conflicting sources are **never silently resolved**; the conflict is recorded on the row
   (see QB map rows for MIA/ARI/BAL).
5. Blanks mean "not confirmed this session" — with the discovery action that would confirm them.

## Known gaps (blanks on the site, by design)

- 20 of 32 teams' home venues are not visible on the official Week 10 schedule page (their Week 10
  games are away/international) → left blank, flagged, discovery action = team official pages.
- Official 2026 depth charts (starters → 2nd/3rd string) — no official NFL source publishes full
  depth charts; team PR releases do. Blocked in this sandbox; see open questions Q3.
- Player props & live odds feed — no reachable licensed odds provider in this sandbox; see Q6.
