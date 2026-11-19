#!/usr/bin/env python3
"""Build verified Reserve/IR, Transactions Turnover, Announced-Starter, and Week 10 Inactive registers.

Covers project brief rows 14, 32, 35, 43, 46, 47, 49, and 65 using only official
NFL.com and official NFL club website pages fetched on 2026-11-19. Every unconfirmed
field (such as snap_count, or the blank Position column on NFL.com monthly transaction
tables) is kept strictly empty ("") and explicitly flagged rather than inferred.

Usage:
  python3 tools/origination_desk/build_roster_audit.py
  python3 tools/origination_desk/build_roster_audit.py --check
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "origination_desk" / "roster"
CAPTURED_DATE = "2026-11-19"

SRC_RESERVE_NOV = "https://www.nfl.com/transactions/league/reserve-list/2026/11"
SRC_RESERVE_OCT = "https://www.nfl.com/transactions/league/reserve-list/2026/10"
SRC_TRADES_NOV = "https://www.nfl.com/transactions/league/trades/2026/11"
SRC_BAL_ROSTER = "https://www.nfl.com/teams/baltimore-ravens/roster"
SRC_MIA_ROSTER = "https://www.nfl.com/teams/miami-dolphins/roster"
SRC_DET_ROSTER = "https://www.nfl.com/teams/detroit-lions/roster"
SRC_COLTS_W10 = "https://www.colts.com/news/colts-release-unofficial-depth-chart-for-week-10"
SRC_COLTS_W11 = "https://www.colts.com/news/colts-release-unofficial-depth-chart-for-week-11"
SRC_INACT_TNF = "https://www.nfl.com/news/week-10-thursday-night-inactives-washington-commanders-at-new-york-giants"
SRC_INACT_SUN = "https://www.nfl.com/news/nfl-week-10-inactives-players-ruled-out-sunday-2026-season"
SRC_INACT_MNF = "https://www.nfl.com/news/week-10-monday-night-inactives-los-angeles-chargers-at-baltimore-ravens"
SRC_INJ_W10 = "https://www.nfl.com/injuries/league/2026/reg10"
SRC_ROUNDUP_1117 = "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-tuesday-nov-17"

# Verbatim official Reserve List rows read from NFL.com monthly transaction pages (25 Nov + 10 key Oct)
# plus club-roster RES confirmations proving why truncated 25-row monthly tables must be paired with club rosters.
# Note: NFL.com monthly transaction tables print an empty Position cell on every row; tx_printed_pos is "" verbatim.
RESERVE_ROWS = [
    # (club, date_2026, player, player_url, tx_printed_pos, roster_verified_pos, status_label, evidence_kind, source_url, note)
    ("PIT", "2026-11-18", "Mason McCormick", "https://www.nfl.com/players/mason-mccormick/", "", "LG", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR 11/18; still listed at LG depth 1 on steelers.com depth chart"),
    ("KC", "2026-11-18", "Jared Wiley", "https://www.nfl.com/players/jared-wiley/", "", "TE", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR 11/18; still listed at TE depth 3 on chiefs.com depth chart"),
    ("DET", "2026-11-18", "Aidan Hutchinson", "https://www.nfl.com/players/aidan-hutchinson/", "", "DE", "Reserve/Injured", "league_tx_and_club_roster", SRC_RESERVE_NOV, "Torn ACL in W10 Munich game; placed on IR 11/18; still listed at EDGE depth 1 on detroitlions.com depth chart"),
    ("MIN", "2026-11-18", "Bo Richter", "https://www.nfl.com/players/bo-richter/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Position cell blank on NFL.com monthly transaction page; not inferred"),
    ("HOU", "2026-11-17", "Azeez Al-Shaair", "https://www.nfl.com/players/azeez-al-shaair/", "", "LB", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR 11/17 ahead of W11 TNF vs IND; Texans depth chart is unparsed image"),
    ("MIA", "2026-11-17", "Zeek Biggers", "https://www.nfl.com/players/zeek-biggers/", "", "DT", "Reserve/Injured", "league_tx_and_club_roster", SRC_RESERVE_NOV, "Confirmed RES on miami-dolphins/roster (#93 DT)"),
    ("MIA", "2026-11-17", "Jordan Phillips", "https://www.nfl.com/players/jordan-phillips-2/", "", "DT", "Reserve/Injured", "league_tx_and_club_roster", SRC_RESERVE_NOV, "Confirmed RES on miami-dolphins/roster (#94 DT)"),
    ("AZ", "2026-11-17", "Andrew Wingard", "https://www.nfl.com/players/andrew-wingard/", "", "S", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Wrist/knee IR placement also confirmed in NFL.com Nov 17 roundup"),
    ("AZ", "2026-11-17", "Jordan Burch", "https://www.nfl.com/players/jordan-burch/", "", "LB", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Knee IR placement also confirmed in NFL.com Nov 17 roundup"),
    ("BUF", "2026-11-17", "Ar'maj Reed-Adams", "https://www.nfl.com/players/ar-maj-reed-adams/", "", "G", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Inactive W10 Sunday; placed on IR 11/17; listed RG2 in depth_chart_pilot.tsv"),
    ("IND", "2026-11-17", "Jaylon Carlies", "https://www.nfl.com/players/jaylon-carlies/", "", "WLB", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Listed WLB1 on Colts 11/16 W11 depth chart release, then placed on IR 11/17"),
    ("TEN", "2026-11-17", "Wan'Dale Robinson", "https://www.nfl.com/players/wan-dale-robinson/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Position cell blank on NFL.com monthly transaction page; not inferred"),
    ("LA", "2026-11-16", "Dylan McMahon", "https://www.nfl.com/players/dylan-mcmahon/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Position cell blank on NFL.com monthly transaction page; not inferred"),
    ("LAC", "2026-11-16", "Branson Taylor", "https://www.nfl.com/players/branson-taylor/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Position cell blank on NFL.com monthly transaction page; not inferred"),
    ("NO", "2026-11-14", "Christen Miller", "https://www.nfl.com/players/christen-miller/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR Saturday 11/14 before W10 Sunday"),
    ("NE", "2026-11-14", "TreVeyon Henderson", "https://www.nfl.com/players/treveyon-henderson/", "", "RB", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Listed Out on W10 injury report, moved to IR 11/14, hence absent from W10 53-man inactive list"),
    ("CLE", "2026-11-14", "Michael Burton", "https://www.nfl.com/players/michael-burton/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR Saturday 11/14"),
    ("IND", "2026-11-14", "Mo Alie-Cox", "https://www.nfl.com/players/mo-alie-cox/", "", "TE", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Groin IR 11/14; removed from Colts W11 depth chart on 11/16"),
    ("IND", "2026-11-14", "Akeem Davis-Gaither", "https://www.nfl.com/players/akeem-davis-gaither/", "", "MLB", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Knee IR 11/14; CJ Allen promoted to MLB1 on Colts W11 depth chart"),
    ("TEN", "2026-11-14", "Peter Skoronski", "https://www.nfl.com/players/peter-skoronski/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR Saturday 11/14"),
    ("TEN", "2026-11-14", "Tommy Townsend", "https://www.nfl.com/players/tommy-townsend/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR Saturday 11/14"),
    ("DAL", "2026-11-14", "Tyler Goodson", "https://www.nfl.com/players/tyler-goodson/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR Saturday 11/14"),
    ("GB", "2026-11-14", "Josh Whyle", "https://www.nfl.com/players/josh-whyle/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR Saturday 11/14"),
    ("LA", "2026-11-12", "Puka Nacua", "https://www.nfl.com/players/puka-nacua/", "", "WR", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Placed on IR 11/12; still listed at WR slot 2 depth 1 on therams.com depth chart"),
    ("LA", "2026-11-10", "Jordan Whittington", "https://www.nfl.com/players/jordan-whittington/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_NOV, "Earliest row shown on truncated 25-row November Reserve List page"),
    # Club-roster RES rows omitted by the 25-row monthly transaction pagination cap (proving VQ-06 / VR-25 / VR-26)
    ("MIA", "2026-11-10", "Malik Willis", "https://www.nfl.com/players/malik-willis/", "", "QB", "RES (Reserve/Injured)", "club_roster_res", SRC_MIA_ROSTER, "VQ-06 proof: absent from weekly injury report because on IR (groin, W10-W13); omitted by 25-row Nov tx pagination"),
    ("MIA", "", "De'Von Achane", "https://www.nfl.com/players/devon-achane/", "", "RB", "RES (Reserve/Injured)", "club_roster_res", SRC_MIA_ROSTER, "Confirmed RES (#28 RB) on official Miami Dolphins nfl.com roster"),
    ("MIA", "", "Zach Sieler", "https://www.nfl.com/players/zach-sieler/", "", "DE", "RES (Reserve/Injured)", "club_roster_res", SRC_MIA_ROSTER, "Confirmed RES (#92 DE) on official Miami Dolphins nfl.com roster"),
    ("BAL", "", "Lamar Jackson", "https://www.nfl.com/players/lamar-jackson/", "", "QB", "RES (Reserve/Injured)", "club_roster_res", SRC_BAL_ROSTER, "VR-17/VR-26 proof: #8 QB RES (right thumb, 6-10 wks); absent from W10 injury report because on IR"),
    ("BAL", "", "Tyler Huntley", "https://www.nfl.com/players/tyler-huntley/", "", "QB", "RES (Reserve/Injured)", "club_roster_res", SRC_BAL_ROSTER, "VR-17/VR-26 proof: #5 QB RES (season-ending turf toe); nflverse games.csv falsely listed as W10 starter"),
    ("BAL", "", "Skylar Thompson", "https://www.nfl.com/players/skylar-thompson/", "", "QB", "RES (Reserve/Injured)", "club_roster_res", SRC_BAL_ROSTER, "Confirmed #11 QB RES on official Baltimore Ravens nfl.com roster"),
    ("DET", "", "Jack Campbell", "https://www.nfl.com/players/jack-campbell-3/", "", "LB", "RES (Reserve/Injured)", "club_roster_res", SRC_DET_ROSTER, "Confirmed #46 LB RES on official Detroit Lions nfl.com roster"),
    ("DET", "", "Isiah Pacheco", "https://www.nfl.com/players/isiah-pacheco/", "", "RB", "RES (Reserve/Injured)", "club_roster_res", SRC_DET_ROSTER, "Confirmed #10 RB RES on official Detroit Lions nfl.com roster"),
    ("DET", "", "Devin White", "https://www.nfl.com/players/devin-white/", "", "LB", "RES (Reserve/Injured)", "club_roster_res", SRC_DET_ROSTER, "Confirmed #45 LB RES on official Detroit Lions nfl.com roster"),
    # High-impact October 2026 league Reserve List rows
    ("KC", "2026-10-31", "L'Jarius Sneed", "https://www.nfl.com/players/l-jarius-sneed/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_OCT, "Placed on IR 10/31; absent from weekly injury report because on IR"),
    ("LAC", "2026-10-31", "Derwin James", "https://www.nfl.com/players/derwin-james/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_OCT, "Placed on IR 10/31; absent from weekly injury report because on IR"),
    ("DEN", "2026-10-31", "RJ Harvey", "https://www.nfl.com/players/rj-harvey/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_OCT, "Placed on IR 10/31"),
    ("NYJ", "2026-10-31", "T'Vondre Sweat", "https://www.nfl.com/players/t-vondre-sweat/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_OCT, "Placed on IR 10/31"),
    ("WAS", "2026-10-28", "Terry McLaurin", "https://www.nfl.com/players/terry-mclaurin/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_OCT, "Placed on IR 10/28; absent from weekly injury report because on IR"),
    ("CAR", "2026-10-27", "Taylor Moton", "https://www.nfl.com/players/taylor-moton/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_OCT, "Placed on IR 10/27"),
    ("NYG", "2026-10-27", "Tyrone Tracy Jr.", "https://www.nfl.com/players/tyrone-tracy-jr/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_OCT, "Placed on IR 10/27"),
    ("IND", "2026-10-27", "Cam Taylor-Britt", "https://www.nfl.com/players/cam-taylor-britt/", "", "", "Reserve/Injured", "league_tx_table", SRC_RESERVE_OCT, "Placed on IR 10/27"),
    ("BUF", "2026-10-26", "C.J. Gardner-Johnson", "https://www.nfl.com/players/chauncey-gardner-johnson/", "", "", "Reserve/Suspended By Commissioner-Less than One Year", "league_tx_table", SRC_RESERVE_OCT, "Reserve/Suspended 10/26; non-injury reserve category"),
]

# All 12 November 2026 trades from https://www.nfl.com/transactions/league/trades/2026/11
TRADES_NOV_ROWS = [
    ("ATL", "JAX", "2026-11-10", "Jessie Bates", "https://www.nfl.com/players/jessie-bates/", "", "Traded", SRC_TRADES_NOV, "Traded at 11/10 deadline; inactive for JAX in W10 Sunday game at TEN during trade acclimation"),
    ("PHI", "JAX", "2026-11-10", "Jordan Davis", "https://www.nfl.com/players/jordan-davis/", "", "Traded", SRC_TRADES_NOV, "Traded at 11/10 deadline; inactive for JAX in W10 Sunday game at TEN during trade acclimation"),
    ("TEN", "BUF", "2026-11-10", "Amani Hooker", "https://www.nfl.com/players/amani-hooker/", "", "Traded", SRC_TRADES_NOV, "Deadline safety trade TEN -> BUF"),
    ("IND", "SF", "2026-11-10", "Keenan Allen", "https://www.nfl.com/players/keenan-allen/", "WR", "Traded", SRC_TRADES_NOV, "Brief row 35: starting WR traded IND -> SF before 4pm ET deadline; documented in Colts W10 depth-chart release"),
    ("LV", "MIN", "2026-11-10", "Kirk Cousins", "https://www.nfl.com/players/kirk-cousins/", "", "Traded", SRC_TRADES_NOV, "Deadline QB trade LV -> MIN with Kyler Murray Out (hamstring)"),
    ("LAC", "DEN", "2026-11-10", "Daiyan Henley", "https://www.nfl.com/players/daiyan-henley/", "", "Traded", SRC_TRADES_NOV, "Deadline trade LAC -> DEN"),
    ("IND", "KC", "2026-11-10", "Josh Downs", "https://www.nfl.com/players/josh-downs/", "WR", "Traded", SRC_TRADES_NOV, "Brief row 35: starting WR traded IND -> KC before 4pm ET deadline; documented in Colts W10 depth-chart release"),
    ("ATL", "BAL", "2026-11-10", "Ryan Neuzil", "https://www.nfl.com/players/ryan-neuzil/", "C", "Traded", SRC_TRADES_NOV, "Traded ATL -> BAL; now listed LG2 and C2 on baltimoreravens.com depth chart"),
    ("BAL", "ATL", "2026-11-10", "Andrew Vorhees", "https://www.nfl.com/players/andrew-vorhees/", "G", "Traded", SRC_TRADES_NOV, "Traded BAL -> ATL; listed TRC on Ravens nfl.com roster"),
    ("NYJ", "DET", "2026-11-09", "Andre Cisco", "https://www.nfl.com/players/andre-cisco/", "", "Traded", SRC_TRADES_NOV, "Pre-deadline trade NYJ -> DET"),
    ("NO", "JAX", "2026-11-09", "Davon Godchaux", "https://www.nfl.com/players/davon-godchaux/", "", "Traded", SRC_TRADES_NOV, "Pre-deadline trade NO -> JAX"),
    ("AZ", "BAL", "2026-11-06", "Jacoby Brissett", "https://www.nfl.com/players/jacoby-brissett/", "QB", "Traded", SRC_TRADES_NOV, "Brief row 47: replacement QB traded AZ -> BAL after Lamar Jackson & Tyler Huntley went on IR; started W10 MNF"),
]

# Announced-starter evidence field (Brief Row 43 — dated official announcements, never inferred from depth rank 2)
ANNOUNCED_STARTERS = [
    ("SEA", 10, "2026_10_SEA_LV", "Drew Lock", "QB", "Sam Darnold", "Out (ribs/quadricep) + W10 Sunday inactive", "2026-11-13",
     "Coach Mike Macdonald announced Friday Nov 13 that Drew Lock has no injury designation and will start Sunday vs. Raiders; Jalen Milroe backup.",
     "https://www.nfl.com/news/drew-lock-no-injury-designation-seahawks-raiders"),
    ("MIA", 10, "2026_10_MIA_IND", "Kyle McCord", "QB", "Malik Willis", "Placed on Reserve/Injured (groin, W10-W13)", "2026-11-13",
     "NFL.com reported Malik Willis placed on IR with groin injury and second-year QB Kyle McCord will fill in starting Sunday at Colts; nflverse mirror still listed Willis.",
     "https://www.nfl.com/news/dolphins-place-qb-malik-willis-groin-on-injured-reserve-kyle-mccord-in-line-for-first-start"),
    ("BAL", 10, "2026_10_LAC_BAL", "Jacoby Brissett", "QB", "Lamar Jackson / Tyler Huntley", "Both on Reserve/Injured (RES); Joe Fagnano started W9", "2026-11-15",
     "Acquired 11/06 from AZ; Ravens HC Jesse Minter confirmed Brissett starting Monday Night Football vs. Chargers (4th Ravens starting QB in 2026); nflverse mirror falsely listed Huntley.",
     "https://www.nfl.com/news/ravens-jesse-minter-very-impressed-by-jacoby-brissett-feels-team-is-refreshed-after-mini-bye-week"),
    ("AZ", 10, "2026_10_LA_ARI", "Carson Beck", "QB", "Gardner Minshew / Jacoby Brissett", "Minshew season-ending UCL surgery; Brissett traded 11/06", "2026-11-11",
     "NFL.com Wednesday Nov 11 roundup: Cardinals' Carson Beck to start vs. Rams; nflverse mirror still listed Gardner Minshew.",
     "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-wednesday-nov-11"),
    ("CLE", 10, "2026_10_HOU_CLE", "Deshaun Watson", "QB", "Deshaun Watson (cleared concussion protocol)", "Entered concussion protocol W9; cleared W10", "2026-11-11",
     "NFL.com Wednesday Nov 11 roundup: Browns to start QB Deshaun Watson vs. Texans; Dillon Gabriel emergency 3rd QB and Taylen Green inactive on Sunday.",
     "https://www.nfl.com/news/nfl-news-roundup-latest-league-updates-from-wednesday-nov-11"),
]

# Verbatim 2026 Week 10 Official 90-Minute Inactives across all 14 games (28 active clubs; CHI, CIN? No: BYEs in W10 were CHI, DEN, PHI, TB!)
INACTIVES_W10_GAMES = [
    ("2026_10_WAS_NYG", "https://www.nfl.com/games/commanders-at-giants-2026-reg-10", SRC_INACT_TNF, {
        "WAS": ["QB Athan Kaliakmanis (emergency third QB)", "TE Colson Yankoff", "C Lucas Patrick", "CB Isaac Yiadom", "DT Ricky Barber", "G Tanoa Togiai"],
        "NYG": ["CB Paulson Adebo", "CB Nikko Reed", "LB Malik Harrison", "OL Josh Sills", "OL J.C. Davis", "TE Thomas Fidone II", "DL Basil Okoye"],
    }),
    ("2026_10_NE_DET", "https://www.nfl.com/games/patriots-at-lions-2026-reg-10", SRC_INACT_SUN, {
        "NE": ["CB Carlton Davis", "FS Brenden Schooler", "OT Dametrious Crownover", "OT Walter Rouse", "C Ben Brown", "QB Behren Morton (emergency third QB)"],
        "DET": ["CB Keith Abney II", "EDGE Ahmed Hassanein", "C Cade Mays", "LB Amen Ogbongbemiga", "CB D.J. Reed", "DL Mekhi Wingo"],
    }),
    ("2026_10_KC_ATL", "https://www.nfl.com/games/chiefs-at-falcons-2026-reg-10", SRC_INACT_SUN, {
        "KC": ["RB Kenneth Walker", "QB Garrett Nussmeier (Emergency 3rd QB)", "RB Jaydn Ott", "CB Melvin Smith", "FB Ben VanSumeren", "OL Jaylon Moore", "DL Peter Woods"],
        "ATL": ["QB Andy Dalton (emergency third quarterback)", "ILB Divine Deablo", "CB Avieon Terrell", "WR Zachariah Branch", "QB Jack Strand", "CB Robert Longerbeam", "OL Cameron Williams"],
    }),
    ("2026_10_HOU_CLE", "https://www.nfl.com/games/texans-at-browns-2026-reg-10", SRC_INACT_SUN, {
        "HOU": ["LB Azeez Al-Shaair", "TE Brevin Jordan", "WR Marvin Harrison Jr.", "RB David Montgomery", "DE Danielle Hunter", "C/G Keylan Rutledge", "G Wyatt Teller"],
        "CLE": ["QB Dillon Gabriel (emergency third QB)", "QB Taylen Green", "LB Justin Jefferson", "CB Noah Igbinoghene", "S Ronnie Hickman", "C Parker Brailsford"],
    }),
    ("2026_10_MIN_GB", "https://www.nfl.com/games/vikings-at-packers-2026-reg-10", SRC_INACT_SUN, {
        "MIN": ["QB Kyler Murray", "WR Jordan Addison", "QB Max Brosmer (emergency third QB)", "WR Jauan Jennings", "LB Blake Cashman", "TE T.J. Hockenson", "DL Tyroin Ingram-Dawkins"],
        "GB": ["RB Josh Jacobs", "RB Pierre Strong Jr.", "LB Zaire Franklin", "G/T Donovan Jennings", "G Kevin Zeitler", "C Sean Rhyan"],
    }),
    ("2026_10_MIA_IND", "https://www.nfl.com/games/dolphins-at-colts-2026-reg-10", SRC_INACT_SUN, {
        "MIA": ["WR Chris Bell", "CB Marcellas Dial Jr.", "C Aaron Brewer", "G/T Caedan Wallace", "TE Justin Joly", "WR Jared Wayne"],
        "IND": ["LB Jaylon Carlies", "QB Riley Leonard (emergency third QB)", "TE Will Mallory", "LS Luke Rhodes", "DT Jerry Tillery", "OT Jalen Travis"],
    }),
    ("2026_10_CAR_NO", "https://www.nfl.com/games/panthers-at-saints-2026-reg-10", SRC_INACT_SUN, {
        "CAR": ["TE Ja'Tavion Sanders", "QB Haynes King (emergency third QB)", "CB Will Lee", "RB AJ Dillon", "LB Bobby Okereke", "C Sam Hecht", "DT TeRah Edwards"],
        "NO": ["QB Zach Wilson (designated third QB)", "S Mike Reid", "RB CJ Donaldson", "LB Jaylan Ford", "OT Taliese Fuaga", "C Erik McCoy"],
    }),
    ("2026_10_BUF_NYJ", "https://www.nfl.com/games/bills-at-jets-2026-reg-10", SRC_INACT_SUN, {
        "BUF": ["QB Shane Buechele", "S Jalon Kilgore", "OLB Mike Danna", "G Ar'maj Reed- Adams", "OL Jude Bowry", "DL Greg Gaines"],
        "NYJ": ["CB Jarvis Brownlee Jr.", "Edge Nate Lynn", "WR Tim Patrick", "LB Trevin Wallace", "TE Jelani Woods"],
    }),
    ("2026_10_JAX_TEN", "https://www.nfl.com/games/jaguars-at-titans-2026-reg-10", SRC_INACT_SUN, {
        "JAX": ["S Jessie Bates III", "WR CJ Williams", "DT Jordan Davis", "DE Wesley Williams", "DT Albert Regis"],
        "TEN": ["WR Carnell Tate", "RB Nick Singleton", "CB Jaylon Jones", "LB Cody Barton", "LB Anthony Hill Jr.", "OT Brandon Crenshaw-Dickson", "DT Jackie Marshall"],
    }),
    ("2026_10_LA_ARI", "https://www.nfl.com/games/rams-at-cardinals-2026-reg-10", SRC_INACT_SUN, {
        "LA": ["QB Ty Simpson (emergency third QB)", "S Maximus Pulley", "LS Joe Cardona", "OLB Darryl Peterson III", "OL Steve Avila", "OL Keagen Trost", "OLB Desjuan Johnson"],
        "AZ": ["QB Joey Aguilar", "CB Starling Thomas V", "LB Eku Leota", "OL Jayden Williams", "OL Jon Gaines II", "OL Hjalte Froholdt"],
    }),
    ("2026_10_SEA_LV", "https://www.nfl.com/games/seahawks-at-raiders-2026-reg-10", SRC_INACT_SUN, {
        "SEA": ["QB Sam Darnold", "RB Emanuel Wilson", "CB Avery Smith", "G Quenton Nelson", "OT Charles Cross", "NT Deven Eastern", "DT Leonard Williams"],
        "LV": ["WR Dont'e Thornton Jr.", "WR Malik Benson", "S Tristin McCollum", "S Dalton Johnson", "G Bryce Cabeldue", "DT Thomas Booker IV"],
    }),
    ("2026_10_SF_DAL", "https://www.nfl.com/games/49ers-at-cowboys-2026-reg-10", SRC_INACT_SUN, {
        "SF": ["QB Kurtis Rourke", "WR Mike Evans", "OL Enrique Cruz Jr.", "LB Tatum Bethune", "WR Brandin Cooks"],
        "DAL": ["S P.J. Locke III", "OLB Donovan Ezeiruaku", "CB Derion Kendrick", "WR Jonathan Mingo", "S Juanyeh Thomas", "G Ajani Cornelius", "TE Jake Ferguson"],
    }),
    ("2026_10_PIT_CIN", "https://www.nfl.com/games/steelers-at-bengals-2026-reg-10", SRC_INACT_SUN, {
        "PIT": ["S DeShon Elliott", "QB Drew Allar", "QB Will Howard (emergency third QB)", "CB Sean Murphy-Bunting", "RB Eli Heidenreich"],
        "CIN": ["S Kyle Dugger", "C Connor Lew", "OT Myles Hinton", "DT Landon Robinson"],
    }),
    ("2026_10_LAC_BAL", "https://www.nfl.com/games/chargers-at-ravens-2026-reg-10", SRC_INACT_MNF, {
        "LAC": ["WR Ladd McConkey", "S Kendall Williamson", "CB Isas Waxter", "OLB Bud Dupree", "WR Brenen Thompson", "DL Justin Eboigbe"],
        "BAL": ["WR Elijah Sarratt", "FS Jaylinn Hawkins", "CB Chandler Rivers", "G Emery Jones", "DT Aeneas Peebles", "QB Kedon Slovis (emergency third QB)"],
    }),
]


def _norm_name(raw: str) -> str:
    s = re.sub(r"^\d+\s+", "", raw.strip())
    s = s.replace("Reed- Adams", "Reed-Adams")
    s = re.sub(r"\s+(Jr\.|Sr\.|II|III|IV|V)$", "", s, flags=re.I)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _parse_inactive_entry(entry: str) -> tuple[str, str, str]:
    note = ""
    m = re.search(r"\(([^)]+)\)\s*$", entry)
    core = entry
    if m:
        note = m.group(1).strip()
        core = entry[: m.start()].strip()
    parts = core.split(None, 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip(), note
    return "", core.strip(), note


def _csv_text(headers: list[str], rows: list[list[object]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(headers)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue()


def build_all() -> dict[str, str]:
    files: dict[str, str] = {}

    # 1. Official Reserve List CSV
    res_headers = [
        "club", "transaction_date", "player", "player_url", "tx_printed_position",
        "roster_verified_position", "reserve_status", "evidence_type", "captured_date",
        "source_url", "audit_note",
    ]
    res_rows = [
        [c, dt, p, purl, txpos, rpos, st, ek, CAPTURED_DATE, surl, note]
        for (c, dt, p, purl, txpos, rpos, st, ek, surl, note) in RESERVE_ROWS
    ]
    files["official_reserve_list_2026_oct_nov.csv"] = _csv_text(res_headers, res_rows)

    # 2. Official November Trades CSV
    tr_headers = [
        "from_club", "to_club", "trade_date", "player", "player_url",
        "tx_printed_position", "verified_position", "transaction_type",
        "captured_date", "source_url", "turnover_impact_note",
    ]
    tr_rows = [
        [fc, tc, dt, p, purl, "", vpos, tt, CAPTURED_DATE, surl, note]
        for (fc, tc, dt, p, purl, vpos, tt, surl, note) in TRADES_NOV_ROWS
    ]
    files["official_trades_nov_2026.csv"] = _csv_text(tr_headers, tr_rows)

    # 3. Announced Starters Evidence CSV
    as_headers = [
        "club", "week", "game_id", "announced_starter", "position",
        "displaced_player", "displaced_reason", "announcement_date",
        "evidence_summary", "source_url",
    ]
    as_rows = [list(r) for r in ANNOUNCED_STARTERS]
    files["announced_starters_evidence.csv"] = _csv_text(as_headers, as_rows)

    # 4. Official Week 10 Inactives CSV (14 games, 28 active clubs)
    inact_headers = [
        "season", "week", "game_id", "club", "printed_position", "player",
        "designation_note", "snap_count", "snap_count_status",
        "game_center_url", "source_url",
    ]
    inact_rows: list[list[object]] = []
    inact_by_club: dict[str, list[str]] = {}
    for gid, gurl, surl, club_map in INACTIVES_W10_GAMES:
        for club, entries in club_map.items():
            inact_by_club.setdefault(club, [])
            for raw in entries:
                pos, player, dnote = _parse_inactive_entry(raw)
                inact_by_club[club].append(player)
                inact_rows.append([
                    2026, 10, gid, club, pos, player, dnote,
                    "",  # snap_count strictly blank: unconfirmed / Game Book PDF rights-gated
                    "UNVERIFIED_BLANK (Game Book PDF omits per-player snap counts & carries reuse notice)",
                    gurl, surl,
                ])
    files["official_inactives_2026_week10.csv"] = _csv_text(inact_headers, inact_rows)

    # 5. Stale Depth & Roster-Turnover Versioning Audit against data/pipeline/depth_charts.json + pilot + Colts/Ravens
    depth_json = json.loads((ROOT / "data" / "pipeline" / "depth_charts.json").read_text(encoding="utf-8"))
    reserve_by_key = {(c, _norm_name(p)): (dt, st, surl, note) for (c, dt, p, _, _, _, st, _, surl, note) in RESERVE_ROWS}
    traded_away_by_key = {(fc, _norm_name(p)): (tc, dt, surl, note) for (fc, tc, dt, p, _, _, _, surl, note) in TRADES_NOV_ROWS}

    stale_headers = [
        "audit_id", "club", "unit", "position", "slot", "depth_rank", "player_printed",
        "issue_class", "roster_event_date", "official_roster_state",
        "depth_chart_source_url", "official_event_source_url", "finding",
    ]
    stale_rows: list[list[object]] = []
    seq = 1
    for r in depth_json.get("rows", []):
        club = r["team_abbrev"]
        key = (club, _norm_name(r["player"]))
        if key in reserve_by_key:
            dt, st, surl, note = reserve_by_key[key]
            stale_rows.append([
                f"SD-{seq:02d}", club, r["unit"], r["position"], r["slot"], r["depth"], r["player"],
                "STALE_DEPTH_ON_RESERVE", dt, st, r["_source_url"], surl,
                f"Club depth chart (retrieved {r['_retrieved_at'][:10]}) still lists {r['player']} at {r['position']} depth {r['depth']} after {st} ({dt or 'roster RES'}).",
            ])
            seq += 1
        elif key in traded_away_by_key:
            tc, dt, surl, note = traded_away_by_key[key]
            stale_rows.append([
                f"SD-{seq:02d}", club, r["unit"], r["position"], r["slot"], r["depth"], r["player"],
                "STALE_DEPTH_TRADED_AWAY", dt, f"Traded to {tc}", r["_source_url"], surl,
                f"Club depth chart still lists {r['player']} after trade to {tc} on {dt}.",
            ])
            seq += 1

    # Explicit structural roster-turnover audit rows required by brief rows 35, 47, 49
    structural_events = [
        [
            f"SD-{seq:02d}", "BAL", "Offense", "QB", 1, 1, "Lamar Jackson / Tyler Huntley -> Jacoby Brissett",
            "TURNOVER_VERSION_RESOLVED_ON_CLUB_STALE_IN_MIRROR", "2026-11-06",
            "Jackson RES + Huntley RES + Brissett Traded AZ->BAL 11/06",
            "https://www.baltimoreravens.com/team/depth-chart", SRC_TRADES_NOV,
            "Brief row 47: Ravens live chart now prints 1. Jacoby Brissett | 2. Joe Fagnano | 3. Kedon Slovis, whereas nflverse games.csv & pre-update captures still carried Huntley/Jackson while both were on RES.",
        ],
        [
            f"SD-{seq + 1:02d}", "IND", "Offense", "WR", 1, 1, "Keenan Allen (to SF) & Josh Downs (to KC)",
            "SAME_DAY_DEPTH_AND_TRADE_TURNOVER", "2026-11-10",
            "Both starting WRs traded prior to 4:00 PM ET deadline",
            SRC_COLTS_W10, SRC_TRADES_NOV,
            "Brief row 35: Colts W10 depth-chart article (11/10 4:27 PM) simultaneously announced trading Keenan Allen to SF and Josh Downs to KC, promoting Laquon Treadwell, Anthony Gould, and Ashton Dulin.",
        ],
        [
            f"SD-{seq + 2:02d}", "IND", "Defense", "WLB", 1, 1, "Jaylon Carlies",
            "POST_RELEASE_IR_STALENESS", "2026-11-17",
            "Placed on Reserve/Injured 11/17 after 11/16 W11 depth release",
            SRC_COLTS_W11, SRC_RESERVE_NOV,
            "Colts W11 depth chart (11/16 4:17 PM) updated MLB1 (CJ Allen for IR'd Akeem Davis-Gaither) and TE2 (Drew Ogletree for IR'd Mo Alie-Cox), then went stale 24h later when WLB1 Jaylon Carlies went on IR 11/17.",
        ],
        [
            f"SD-{seq + 3:02d}", "DET", "Defense", "S / C / CB", 1, 1, "Kerby Joseph / Cade Mays / D.J. Reed",
            "INJURY_OUT_VS_53MAN_INACTIVE_SPLIT", "2026-11-15",
            "All 3 Out on W10 report; Mays & Reed W10 inactive; Joseph pre-activation PUP/IR window",
            SRC_INJ_W10, SRC_ROUNDUP_1117,
            "Brief row 49: Cade Mays and D.J. Reed were deactivated on Sunday's 53-man Munich inactive list, whereas Kerby Joseph (out since W6 2025, expected W11 debut vs TB) was Out on the injury report without consuming a 53-man inactive slot.",
        ],
        [
            f"SD-{seq + 4:02d}", "HOU", "All", "ALL", "", "", "",
            "IMAGE_ONLY_CLUB_DEPTH_CHART", "2026-11-19",
            "0 parsable HTML rows on houstontexans.com/team/depth-chart",
            "https://www.houstontexans.com/team/depth-chart", SRC_RESERVE_NOV,
            "Brief row 45: Texans publish depth chart as image/non-table markup; depth cells left blank (never eye-transcribed), while LB Azeez Al-Shaair was confirmed placed on IR 11/17.",
        ],
    ]
    stale_rows.extend(structural_events)
    files["stale_depth_and_turnover_audit.csv"] = _csv_text(stale_headers, stale_rows)

    # 6. Per-Team 32-Club Availability & Starter/Replacement View (Brief Row 65)
    # Join data/nfl/injuries_week10.tsv + data/pipeline/depth_charts.json + our W10 inactives & Oct-Nov IRs
    standings_clubs: list[tuple[str, str, str]] = []
    for line in (ROOT / "data" / "nfl" / "standings.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or line.startswith("abbr\t"):
            continue
        parts = line.split("\t")
        standings_clubs.append((parts[0], parts[1], parts[17]))
    standings_clubs.sort(key=lambda x: x[0])

    # Build starter -> 2nd string lookup from depth_charts.json (stripping GB leading jersey numbers)
    starters_by_club: dict[str, dict[str, tuple[str, str, str]]] = {}
    slot_map: dict[tuple[str, str, str, int], dict[int, str]] = {}
    club_chart_url: dict[str, str] = {}
    for r in depth_json.get("rows", []):
        c = r["team_abbrev"]
        club_chart_url[c] = r["_source_url"]
        k = (c, r["unit"], r["position"], int(r["slot"]))
        slot_map.setdefault(k, {})[int(r["depth"])] = re.sub(r"^\d+\s+", "", r["player"]).strip()
    for (c, unit, pos, slot), dmap in slot_map.items():
        if 1 in dmap:
            s1 = dmap[1]
            s2 = dmap.get(2, "")
            starters_by_club.setdefault(c, {})[_norm_name(s1)] = (pos, s1, s2)

    inj_rows_by_club: dict[str, list[dict[str, str]]] = {}
    for line in (ROOT / "data" / "nfl" / "injuries_week10.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or line.startswith("game\t"):
            continue
        parts = line.split("\t")
        if len(parts) >= 8:
            inj_rows_by_club.setdefault(parts[1], []).append({
                "player": parts[2], "pos": parts[3], "practice": parts[5], "status": parts[6], "url": parts[7],
            })

    w10_byes = {"CHI", "DEN", "PHI", "TB"}
    club_headers = [
        "club", "team_name", "w10_slate_state", "w10_injury_report_rows",
        "w10_ruled_out_or_doubtful", "w10_questionable", "club_chart_starters_out",
        "named_2nd_string_replacements", "unnamed_starter_replacements",
        "w10_official_inactives_count", "verified_oct_nov_reserve_count",
        "depth_source_status", "team_source_url", "injury_source_url",
    ]
    club_summary_rows: list[list[object]] = []
    for abbr, tname, turl in standings_clubs:
        irows = inj_rows_by_club.get(abbr, [])
        out_d = [x for x in irows if x["status"] in ("Out", "Doubtful")]
        quest = [x for x in irows if x["status"] == "Questionable"]
        smap = starters_by_club.get(abbr, {})
        starters_out_list: list[str] = []
        named_rep_list: list[str] = []
        unnamed_cnt = 0
        if abbr != "HOU":
            for x in out_d:
                nk = _norm_name(x["player"])
                if nk in smap:
                    pos, s1, s2 = smap[nk]
                    starters_out_list.append(f"{s1} ({pos})")
                    if s2:
                        named_rep_list.append(f"{s2} for {s1}")
                    else:
                        unnamed_cnt += 1
        inact_cnt: object = "" if abbr in w10_byes else len(inact_by_club.get(abbr, []))
        res_cnt = sum(1 for r in RESERVE_ROWS if r[0] == abbr)
        club_summary_rows.append([
            abbr,
            tname,
            "BYE_WEEK_10" if abbr in w10_byes else "ACTIVE_WEEK_10",
            "" if abbr in w10_byes else len(irows),
            "" if abbr in w10_byes else len(out_d),
            "" if abbr in w10_byes else len(quest),
            "" if abbr in ("HOU",) or abbr in w10_byes else ("; ".join(starters_out_list) if starters_out_list else "0 listed starters Out"),
            "" if abbr in ("HOU",) or abbr in w10_byes else ("; ".join(named_rep_list) if named_rep_list else ""),
            "" if abbr in ("HOU",) or abbr in w10_byes else unnamed_cnt,
            inact_cnt,
            res_cnt,
            "UNAVAILABLE_IMAGE_CHART (blank, not inferred)" if abbr == "HOU" else "CLUB_HTML_PARSED (unofficial self-report)",
            club_chart_url.get(abbr, turl),
            SRC_INJ_W10,
        ])
    files["club_availability_summary_w10_w11.csv"] = _csv_text(club_headers, club_summary_rows)

    summary = {
        "dataset": "origination_desk_roster_audit",
        "captured_date": CAPTURED_DATE,
        "counts": {
            "reserve_rows_verified": len(res_rows),
            "november_trades_verified": len(tr_rows),
            "announced_starters_verified": len(as_rows),
            "week10_inactive_games_verified": len(INACTIVES_W10_GAMES),
            "week10_inactive_players_verified": len(inact_rows),
            "stale_depth_and_turnover_flags": len(stale_rows),
            "clubs_summarized": len(club_summary_rows),
        },
        "key_findings": [
            "NFL.com monthly Reserve List page (2026/11) truncates at 25 rows (stopping at 11/10) and prints a blank Position cell on every row; club roster RES tables are required to catch Malik Willis (MIA QB), Lamar Jackson (BAL QB), and Tyler Huntley (BAL QB).",
            "Live club depth charts retrieved 2026-11-19 still list multiple newly IR'd starters at depth 1: Aidan Hutchinson (DET EDGE1, IR 11/18), Jaylon Carlies (IND WLB1, IR 11/17), Mason McCormick (PIT LG1, IR 11/18), and Puka Nacua (LA WR1, IR 11/12).",
            f"All {len(INACTIVES_W10_GAMES)} Week 10 games (28 active clubs, {len(inact_rows)} player deactivations) are transcribed from the 3 official 2026 NFL.com inactives releases; snap counts remain blank pending an authorized snap-count source.",
            "Lions Week 10 Out reconciliation: Cade Mays and D.J. Reed appear on Sunday's 6-man Munich inactive list, while Kerby Joseph (out since W6 2025, expected W11 debut vs TB) was Out on the injury report prior to 53-man activation.",
        ],
        "file_sha256": {
            name: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for name, content in sorted(files.items())
        },
    }
    files["roster_audit_summary.json"] = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify committed files match deterministic output")
    args = ap.parse_args()

    files = build_all()
    if args.check:
        diffs: list[str] = []
        for name, content in sorted(files.items()):
            p = OUT_DIR / name
            if not p.exists():
                diffs.append(f"missing {p.relative_to(ROOT)}")
            elif p.read_text(encoding="utf-8") != content:
                diffs.append(f"stale {p.relative_to(ROOT)}")
        if diffs:
            print("FAIL roster audit check:", "; ".join(diffs))
            return 1
        print(f"OK: {len(files)} roster-audit files verified up to date in {OUT_DIR.relative_to(ROOT)}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(files.items()):
        (OUT_DIR / name).write_text(content, encoding="utf-8")
    print(f"Wrote {len(files)} files to {OUT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
