"""Source registry and evidence tiers.

Tier policy (enforced by tools/verify_console.py):
  official  - published by the league (nfl.com, operations.nfl.com) or by a club
              on its own site. A row may be presented as league-verified.
  mirror    - a third-party redistribution of league data that this repository
              can fingerprint (nflverse/nfldata). Usable, never called official.
  computed  - arithmetic performed in this repository over official/mirror rows.
              Must name the inputs it was computed from.
  none      - no source exists. The cell is emitted blank and flagged.
"""

TIERS = ("official", "mirror", "computed", "none")

SOURCES = {
    "nfl_standings": {
        "tier": "official",
        "org": "NFL",
        "url": "https://www.nfl.com/standings/league/2026/REG",
        "label": "NFL.com - 2026 League Standings",
        "note": "32 clubs x 16 fields. Re-fetched and compared cell by cell.",
    },
    "nfl_schedule": {
        "tier": "official",
        "org": "NFL",
        "url": "https://www.nfl.com/schedules/2026/by-week/week-10",
        "label": "NFL.com - Week 10 Schedule",
        "note": "14 games plus the league's own 'Teams on Bye' list.",
    },
    "nfl_injuries": {
        "tier": "official",
        "org": "NFL",
        "url": "https://www.nfl.com/injuries/",
        "label": "NFL.com - Official Injury Report, Week 10 2026",
        "note": "345 rows across the 28 clubs playing this week.",
    },
    "nfl_team_stats": {
        "tier": "official",
        "org": "NFL",
        "url": "https://www.nfl.com/stats/team-stats/offense/passing/2026/reg/all",
        "label": "NFL.com - 2026 Team Stats",
        "note": "Per-row _source_url is carried through from data/pipeline/team_stats.json.",
    },
    "nfl_scores": {
        "tier": "official",
        "org": "NFL",
        "url": "https://www.nfl.com/scores/",
        "label": "NFL.com - Scores",
        "note": "Official final scores. Not fetched row by row in this pass; the mirror's "
                "scores are reconciled against the league's own standings instead (160/160).",
    },
    "club_depth_chart": {
        "tier": "official",
        "org": "NFL club",
        "url": "https://www.nfl.com/teams/",
        "label": "Club depth chart (one page per club, linked per row)",
        "note": "Club-published, not a league fact. Each row links its own club page.",
    },
    "nfldata_games": {
        "tier": "mirror",
        "org": "nflverse/nfldata",
        "url": "https://github.com/nflverse/nfldata/blob/master/data/games.csv",
        "label": "nflverse/nfldata games.csv",
        "note": "7,548 games 1999-2026 with official final scores and one line per game. "
                "The mirror publishes no book identifier and no line timestamp.",
        "sha256": "60ea2f76bd2c539c3080b8efbb7863710284c9afe173b8399a1a1191bf03d5c8",
    },
    "nfldata_closing_lines": {
        "tier": "mirror",
        "org": "nflverse/nfldata",
        "url": "https://github.com/nflverse/nfldata/blob/master/data/closing_lines.csv",
        "label": "nflverse/nfldata closing_lines.csv",
        "note": "20,490 rows, 2006-2018, with odds and settled outcome per side.",
        "sha256": "3571e1c9fc8d7396f405fb7c17d43c15676d335ffc932fbb03ff18da691d1729",
    },
    "nfldata_initial_lines": {
        "tier": "mirror",
        "org": "nflverse/nfldata",
        "url": "https://github.com/nflverse/nfldata/blob/master/data/initial_lines.csv",
        "label": "nflverse/nfldata initial_lines.csv",
        "note": "1,088 rows, 2021 season only, sportsbook WSGT. The only genuine "
                "OPENING lines available to this repository.",
    },
    "nfldata_standings": {
        "tier": "mirror",
        "org": "nflverse/nfldata",
        "url": "https://github.com/nflverse/nfldata/blob/master/data/standings.csv",
        "label": "nflverse/nfldata standings.csv",
        "note": "Used only as a cross-check input, never as a published source.",
    },
    "computed_model": {
        "tier": "computed",
        "org": "this repository",
        "url": "https://github.com/karagemop466-tech/X1/blob/main/src/console/originate.py",
        "label": "X1 walk-forward model (src/console/originate.py)",
        "note": "Fitted only on seasons earlier than the season being predicted.",
    },
    "none": {
        "tier": "none",
        "org": "",
        "url": "",
        "label": "No source exists for this value",
        "note": "Emitted blank and flagged.",
    },
}

# Hosts that count as league-official for the link checker.
OFFICIAL_HOSTS = {
    "www.nfl.com", "nfl.com", "operations.nfl.com", "www.nflfootballops.com",
}
# Hosts that count as a documented, fingerprinted third-party mirror.
MIRROR_HOSTS = {"github.com", "raw.githubusercontent.com", "api.github.com"}
# Club sites: every row links its own club page, so any *.club host is accepted
# only when it appears in data/verify/official_club_sites_2026.psv.


def get(key):
    return SOURCES.get(key, SOURCES["none"])


def tier(key):
    return get(key)["tier"]


def url(key):
    return get(key)["url"]


def label(key):
    return get(key)["label"]
