# Week 10 official injury report — row-level re-capture check

Source: https://www.nfl.com/injuries/ (NFL.com, read 2026-11-15 UTC by session `arena-ed8c600d-x1`).

Official transcription SHA-256: `1a900362786e86664611800917c72549e927bf50f6d6147d79c6703d9fcda033`

- Official rows: **347** across 14 games and 28 clubs
- Published rows (`data/nfl/injuries_week10.tsv`): **345** across 14 games and 28 clubs
- Official rows missing from published table: **2**
- Published rows not on official page: **0**
- Field mismatches on matched rows (injury / practice / game status): **32** cells in **16** rows
- Summary counts, official page vs. counts printed on the published page: {'Out': 70, 'Questionable': 90, 'Doubtful': 11, 'no game status': 176} vs {'Out': 66, 'Questionable': 84, 'Doubtful': 10, 'no game status': 185}

## Per game

| Game | Official rows | Published rows |
|---|---:|---:|
| BUF@NYJ | 23 | 23 |
| CAR@NO | 24 | 24 |
| HOU@CLE | 28 | 28 |
| JAX@TEN | 23 | 23 |
| KC@ATL | 24 | 24 |
| LAC@BAL | 29 | 27 |
| LAR@AZ | 29 | 29 |
| MIA@IND | 25 | 25 |
| MIN@GB | 30 | 30 |
| NE@DET | 24 | 24 |
| PIT@CIN | 17 | 17 |
| SEA@LV | 20 | 20 |
| SF@DAL | 31 | 31 |
| WAS@NYG | 20 | 20 |

## Per club

| Club | Official rows | Published rows |
|---|---:|---:|
| ATL | 11 | 11 |
| AZ | 15 | 15 |
| BAL | 10 | 8 |
| BUF | 14 | 14 |
| CAR | 12 | 12 |
| CIN | 9 | 9 |
| CLE | 12 | 12 |
| DAL | 19 | 19 |
| DET | 9 | 9 |
| GB | 17 | 17 |
| HOU | 16 | 16 |
| IND | 14 | 14 |
| JAX | 11 | 11 |
| KC | 13 | 13 |
| LAC | 19 | 19 |
| LAR | 14 | 14 |
| LV | 5 | 5 |
| MIA | 11 | 11 |
| MIN | 13 | 13 |
| NE | 15 | 15 |
| NO | 12 | 12 |
| NYG | 11 | 11 |
| NYJ | 9 | 9 |
| PIT | 8 | 8 |
| SEA | 15 | 15 |
| SF | 12 | 12 |
| TEN | 12 | 12 |
| WAS | 9 | 9 |

## Missing from published table

| Game | Club | Player | Injury | Practice | Game status |
|---|---|---|---|---|---|
| LAC@BAL | BAL | Calais Campbell |  | Did Not Participate In Practice |  |
| LAC@BAL | BAL | Ronnie Stanley |  | Did Not Participate In Practice |  |

## Field mismatches

| Game | Club | Player | Field | Official | Published |
|---|---|---|---|---|---|
| MIA@IND | IND | Arden Key | injury |  | Hamstring |
| MIA@IND | IND | Arden Key | game_status |  | Questionable |
| LAC@BAL | LAC | Kayode Awosika | injury | Fibula |  |
| LAC@BAL | LAC | Kayode Awosika | practice_status | Full Participation in Practice | Limited Participation in Practice |
| LAC@BAL | LAC | Kayode Awosika | game_status | Questionable |  |
| LAC@BAL | LAC | Bud Dupree | practice_status | Full Participation in Practice | Did Not Participate In Practice |
| LAC@BAL | LAC | Justin Eboigbe | injury | Ankle |  |
| LAC@BAL | LAC | Justin Eboigbe | game_status | Questionable |  |
| LAC@BAL | LAC | Ladd McConkey | injury | Back |  |
| LAC@BAL | LAC | Ladd McConkey | game_status | Questionable |  |
| LAC@BAL | LAC | Keaton Mitchell | practice_status | Full Participation in Practice | Limited Participation in Practice |
| LAC@BAL | LAC | David Njoku | injury | Fibula |  |
| LAC@BAL | LAC | David Njoku | practice_status | Full Participation in Practice | Limited Participation in Practice |
| LAC@BAL | LAC | David Njoku | game_status | Questionable |  |
| LAC@BAL | LAC | Denzel Perryman | injury | Pectoral |  |
| LAC@BAL | LAC | Denzel Perryman | game_status | Questionable |  |
| LAC@BAL | LAC | Trey Pipkins | injury | Not injury related - personal matter, Knee |  |
| LAC@BAL | LAC | Trey Pipkins | practice_status | Limited Participation in Practice | Did Not Participate In Practice |
| LAC@BAL | LAC | Trey Pipkins | game_status | Questionable |  |
| LAC@BAL | LAC | Rodney Shelley | practice_status | Full Participation in Practice | Limited Participation in Practice |
| LAC@BAL | LAC | Branson Taylor | injury | Ankle |  |
| LAC@BAL | LAC | Branson Taylor | game_status | Out |  |
| LAC@BAL | LAC | Brenen Thompson | injury | Hamstring |  |
| LAC@BAL | LAC | Brenen Thompson | game_status | Doubtful |  |
| LAC@BAL | LAC | Isas Waxter | injury | Ankle |  |
| LAC@BAL | LAC | Isas Waxter | game_status | Out |  |
| LAC@BAL | LAC | Kendall Williamson | injury | Calf |  |
| LAC@BAL | LAC | Kendall Williamson | game_status | Out |  |
| LAC@BAL | BAL | Jaylinn Hawkins | injury | Knee |  |
| LAC@BAL | BAL | Jaylinn Hawkins | game_status | Out |  |
| LAC@BAL | BAL | Adam Randall | injury | Neck, Hamstring |  |
| LAC@BAL | BAL | Adam Randall | game_status | Questionable |  |
