"""Rule profiles for regulation kickoffs only. No declaration or effect is inferred."""
from dataclasses import dataclass
from datetime import date
import re


@dataclass(frozen=True)
class Regime:
    season: int
    declaration_source_date: date
    first_quarter: int
    trailing_only: bool
    kickoff_note: str
    declaration_source: str
    kickoff_source: str


REGIMES = {r.season: r for r in (
    Regime(2024, date(2024, 9, 5), 4, True,
           'Dynamic kickoff introduced. A kick directly through the end zone gives the receiving team the 30; landing-zone touchbacks are different.',
           'https://www.nfl.com/news/2024-nfl-season-explaining-rules-for-new-dynamic-kickoff',
           'https://www.nfl.com/news/2024-nfl-season-explaining-rules-for-new-dynamic-kickoff'),
    Regime(2025, date(2025, 5, 21), 1, True,
           'Dynamic kickoff made permanent. A kick directly through the end zone gives the receiving team the 35. Setup-zone alignment also changed.',
           'https://www.nfl.com/news/lions-withdraw-playoff-reseeding-proposal-at-spring-league-meeting',
           'https://operations.nfl.com/the-rules/rules-changes/2025-rules-changes'),
    Regime(2026, date(2026, 3, 31), 1, False,
           'Receiving alignment changed again; Rule 6-1-5 changes the touchback spot specifically for kickoffs from midfield. Do not apply this exception to every kick.',
           'https://media.nfl.com/football-information/2026/news/approved-2026-playing-rules--bylaws-and-resolutions',
           'https://operations.nfl.com/rules-officiating/2026-nfl-rulebook'),
)}


def may_declare(season, quarter, kicking_margin):
    """Eligibility, not attempt probability. Unknown or out-of-scope state → None."""
    rule = REGIMES.get(season)
    if not rule or type(quarter) is not int or quarter not in range(1, 5):
        return None
    if type(kicking_margin) is not int:
        return None
    return quarter >= rule.first_quarter and (not rule.trailing_only or kicking_margin < 0)


def prior_finals(rows, season, as_of):
    """Comparable REG finals in the verified feed. Dates lack times: exclude same-day reads.

    season is the NFL season, not the calendar year of a January game. Each
    registered season has a distinct kickoff profile; never pool across them.
    """
    rule = REGIMES.get(season)
    if not rule or as_of <= rule.declaration_source_date:
        return []
    eligible, seen = [], set()
    for r in rows:
        game = r['game_id']
        m = re.fullmatch(r'(\d{4})_(\d{2})_[A-Z0-9]+_[A-Z0-9]+', game)
        if not m:
            raise ValueError(f'Invalid game id: {game}')
        if int(m[1]) != season:
            continue
        week = int(m[2])
        if (not 1 <= week <= 18 or week != int(r['week']) or
                r['source_url'] != f'https://www.nfl.com/schedules/{season}/by-week/week-{week}' or
                not re.fullmatch(r'https://www\.nfl\.com/games/[a-z0-9-]+-at-[a-z0-9-]+-'
                                 + f'{season}-reg-{week}', r['game_url'])):
            raise ValueError(f'Invalid official regular-season fixture: {game}')
        played, read = map(date.fromisoformat, (r['date_iso'], r['retrieved_at']))
        if read < played or game in seen:
            raise ValueError(f'Invalid read chronology or duplicate: {game}')
        seen.add(game)
        if read < as_of:
            eligible.append(r)
    return eligible
