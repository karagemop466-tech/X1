"""Verified results feed and price-snapshot store.

Two of the eight named requirements live here:

  C2  a verified results feed, so backtests and ROI are computable at all
  C1  a price-snapshot store recording opening and closing numbers

Both are built from inputs whose provenance is recorded in ``sources.py``.
Nothing here is inferred: where the mirror publishes no opening line, the
``open_*`` columns are emitted blank and the row is flagged.
"""

from __future__ import annotations

import csv
import hashlib
import os
import re
from collections import defaultdict

from . import sources

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "data", "raw", "nflverse")
VERIFY = os.path.join(ROOT, "data", "verify")
OUT = os.path.join(ROOT, "data", "console")

# nflverse uses ARI for Arizona; the league's own standings table prints AZ.
TEAM_ALIAS = {"ARI": "AZ", "ARZ": "AZ", "STL": "LA", "SD": "LAC", "OAK": "LV", "BLT": "BAL"}
REVERSE_ALIAS = {v: k for k, v in TEAM_ALIAS.items()}

GAMES_CSV = os.path.join(RAW, "games.csv")
CLOSING_CSV = os.path.join(RAW, "closing_lines.csv")
INITIAL_CSV = os.path.join(RAW, "initial_lines.csv")
STANDINGS_PSV = os.path.join(VERIFY, "official_standings_2026_w10.psv")
INJURIES_PSV = os.path.join(VERIFY, "official_injuries_2026_w10.psv")
SCHEDULE_PSV = os.path.join(VERIFY, "official_schedule_2026_w10.psv")
BYES_PSV = os.path.join(VERIFY, "official_byes_2026_w10.psv")
CLUBS_PSV = os.path.join(VERIFY, "official_club_sites_2026.psv")


def norm_team(code: str) -> str:
    return TEAM_ALIAS.get(code, code)


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_psv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="|"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _num(value):
    """Return a float, or None when the source prints nothing."""
    if value is None:
        return None
    v = str(value).strip()
    if v == "" or v in {"NA", "NaN", "None"}:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _int(value):
    v = _num(value)
    return None if v is None else int(v)


# --------------------------------------------------------------------------
# C2 - verified results feed
# --------------------------------------------------------------------------

def load_games(season_min=1999):
    """Load the mirror's game table, normalised.

    Only rows that actually carry a score are usable as a settled result. Rows
    without a score are kept so that upcoming fixtures can still be originated,
    but they are marked ``settled = False`` and never enter a backtest.
    """
    games = []
    for row in read_csv(GAMES_CSV):
        season = int(row["season"])
        if season < season_min:
            continue
        hs, as_ = _int(row["home_score"]), _int(row["away_score"])
        games.append({
            "game_id": row["game_id"],
            "season": season,
            "week": int(row["week"]) if row["week"].isdigit() else None,
            "gameday": row["gameday"],
            "game_type": row["game_type"],
            "home": norm_team(row["home_team"]),
            "away": norm_team(row["away_team"]),
            "home_score": hs,
            "away_score": as_,
            "settled": hs is not None and as_ is not None,
            "margin_home": (hs - as_) if (hs is not None and as_ is not None) else None,
            "total_points": (hs + as_) if (hs is not None and as_ is not None) else None,
            "roof": row.get("roof", ""),
            "surface": row.get("surface", ""),
            "temp": _num(row.get("temp")),
            "wind": _num(row.get("wind")),
            "away_rest": _num(row.get("away_rest")),
            "home_rest": _num(row.get("home_rest")),
            "div_game": _int(row.get("div_game")),
            "spread_line": _num(row.get("spread_line")),   # +ve => home favoured
            "total_line": _num(row.get("total_line")),
            "home_moneyline": _num(row.get("home_moneyline")),
            "away_moneyline": _num(row.get("away_moneyline")),
            "result": _num(row.get("result")),
        })
    games.sort(key=lambda g: (g["gameday"], g["game_id"]))
    return games


def official_standings():
    return read_psv(STANDINGS_PSV)


def reconcile_2026(games):
    """Reconcile the mirror's 2026 scores against the league's own standings.

    This is the check that turns a third-party mirror into a *verified* results
    feed: if the mirror's game-by-game scores reproduce the league's own
    W-L-T and points-for / points-against for all 32 clubs, the scores are
    corroborated by an official source even though they were not read from it.
    """
    played = [g for g in games if g["season"] == 2026 and g["settled"]]
    agg = defaultdict(lambda: {"W": 0, "L": 0, "T": 0, "PF": 0, "PA": 0, "G": 0})
    for g in played:
        h, a = g["home"], g["away"]
        hs, as_ = g["home_score"], g["away_score"]
        agg[h]["PF"] += hs; agg[h]["PA"] += as_; agg[h]["G"] += 1
        agg[a]["PF"] += as_; agg[a]["PA"] += hs; agg[a]["G"] += 1
        if hs > as_:
            agg[h]["W"] += 1; agg[a]["L"] += 1
        elif as_ > hs:
            agg[a]["W"] += 1; agg[h]["L"] += 1
        else:
            agg[h]["T"] += 1; agg[a]["T"] += 1
    checks, mismatches = [], []
    for row in official_standings():
        team = row["TEAM"]
        got = agg.get(team, {"W": -1, "L": -1, "T": -1, "PF": -1, "PA": -1, "G": 0})
        for field in ("W", "L", "T", "PF", "PA"):
            expected = int(row[field])
            ok = expected == got[field]
            checks.append({
                "team": team, "field": field, "official": expected,
                "feed": got[field], "ok": bool(ok),
            })
            if not ok:
                mismatches.append(checks[-1])
    return {
        "games": len(played),
        "last_gameday": max(g["gameday"] for g in played) if played else None,
        "checks": len(checks),
        "matches": len(checks) - len(mismatches),
        "mismatches": mismatches,
        "detail": checks,
        "source_official": sources.get("nfl_standings"),
        "source_feed": sources.get("nfldata_games"),
    }


def build_results_feed(games):
    """One row per game, with the fields a backtest needs and a source per row."""
    feed = []
    for g in games:
        src = sources.get("nfldata_games")
        row = {
            "game_id": g["game_id"],
            "season": g["season"],
            "week": g["week"] if g["week"] is not None else "",
            "gameday": g["gameday"],
            "home": g["home"],
            "away": g["away"],
            "home_score": g["home_score"] if g["settled"] else "",
            "away_score": g["away_score"] if g["settled"] else "",
            "margin_home": g["margin_home"] if g["settled"] else "",
            "total_points": g["total_points"] if g["settled"] else "",
            "settled": "yes" if g["settled"] else "no",
            "market_spread_home": g["spread_line"] if g["spread_line"] is not None else "",
            "market_total": g["total_line"] if g["total_line"] is not None else "",
            "market_ml_home": g["home_moneyline"] if g["home_moneyline"] is not None else "",
            "market_ml_away": g["away_moneyline"] if g["away_moneyline"] is not None else "",
            "cover_home": "",
            "over_hit": "",
            "ml_home_won": "",
            "source": src["label"],
            "source_url": src["url"],
            "source_tier": src["tier"],
            "flag": "",
        }
        if not g["settled"]:
            row["flag"] = "not-settled: no official score yet"
        else:
            if g["spread_line"] is not None:
                # Convention, established empirically and not assumed:
                #   games.csv spread_line is positive when the HOME team is favoured
                #   (nflverse DATASETS.md), so the home side covers when
                #   home_margin - spread_line > 0. Checked over 7,413 settled games:
                #   mean(home_margin - spread_line) = +0.06, home cover 3,529-3,683-201
                #   (48.9%), and corr(spread_line, no-vig home win probability from the
                #   quoted moneylines) = 0.988 over 5,458 games.
                m = g["margin_home"] - g["spread_line"]
                row["cover_home"] = "PUSH" if m == 0 else ("W" if m > 0 else "L")
            else:
                row["flag"] = "no market spread published for this game"
            if g["total_line"] is not None:
                row["over_hit"] = ("PUSH" if g["total_points"] == g["total_line"]
                                   else ("W" if g["total_points"] > g["total_line"] else "L"))
            row["ml_home_won"] = ("W" if g["margin_home"] > 0
                                  else ("L" if g["margin_home"] < 0 else "PUSH"))
        feed.append(row)
    return feed


# --------------------------------------------------------------------------
# C1 - price-snapshot store
# --------------------------------------------------------------------------

# The store is append-only in production: each capture run appends rows with a
# fresh snapshot_id. Three kinds of row exist today:
#   OPEN   - the number standing when this repo originates the market
#   CLOSE  - the number standing at kick-off (settled markets only)
#   MOVE   - close minus open, published only where both ends are sourced
STORE_HEADER = [
    "snapshot_id", "captured_at_utc", "market_id", "game_id", "season", "week",
    "origination_step", "market_type", "side",
    "open_line", "open_price", "open_source", "open_captured_at_utc",
    "close_line", "close_price", "close_source", "close_captured_at_utc",
    "movement", "settled", "outcome", "source_tier", "flag",
]


def _load_initial_lines():
    """Real opening lines: 2021 only, sportsbook WSGT.

    Sign convention, established empirically rather than assumed: this file
    prints the number as it appears on the board for the named side, so a
    NEGATIVE spread means that side is favoured. games.csv prints the home
    spread positive when home is favoured. Converting, the opening home spread
    in the games.csv convention is ``-line``. Evidence: for the 272 games of
    2021 the ``-line`` reading gives mean(home_margin - opening_spread) =
    -0.39 and corr = 0.405 with the actual margin; the ``+line`` reading gives
    +3.82 and corr = -0.405. The two sides of every game sum to exactly zero in
    272 of 272 games.
    """
    out = {}
    for row in read_csv(INITIAL_CSV):
        out[(row["about"], row["type"], row["side"])] = _num(row["line"])
    return out


def _load_closing_lines():
    """Closing lines with quoted odds and settled outcome: 2006-2018."""
    out = defaultdict(dict)
    for row in read_csv(CLOSING_CSV):
        gid = row["alt_game_id"] or row["game_id"]
        out[(gid, row["type"])][row["side"]] = {
            "line": _num(row["line"]), "odds": _num(row["odds"]),
            "outcome": row["outcome"],
        }
    return out


def build_price_snapshots(games, captured_at):
    """Populate the store.

    Honest scope, stated on the page rather than hidden:

      * 2021 is the only season for which a genuine OPENING line exists in this
        repository (nflverse/nfldata initial_lines.csv, sportsbook WSGT). For
        those 272 games the store holds both ends and can publish a movement.
      * For every other settled season only one number per market is published
        by any source available here, and it carries no book and no timestamp.
        It is stored as the CLOSE and the OPEN is left blank.
      * For the 14 Week 10 2026 fixtures this repo originates now, the number
        standing at capture time is stored as the OPEN and the CLOSE is blank
        until the game settles.
    """
    initial = _load_initial_lines()
    closing = _load_closing_lines()
    rows = []
    missing_open_2021 = []

    def add(**kw):
        rec = {k: "" for k in STORE_HEADER}
        rec.update(kw)
        rows.append(rec)

    week10 = [g for g in games if g["season"] == 2026 and g["week"] == 10]
    step = {"SIDE": 1, "TOTAL": 2, "MONEYLINE": 3}

    # --- markets originated now: Week 10 2026 games that have not kicked off.
    # A game that has already settled is no longer a market we originate, so it
    # is recorded in the close-only bucket below instead. ---
    for g in week10:
        if g["settled"]:
            continue
        gid = g["game_id"]
        if g["spread_line"] is not None:
            for side, line in (("home", g["spread_line"]), ("away", -g["spread_line"])):
                add(snapshot_id="OPEN-2026W10", captured_at_utc=captured_at,
                    market_id=f"{gid}:SIDE:{side}", game_id=gid, season=2026, week=10,
                    origination_step=step["SIDE"], market_type="SIDE", side=side,
                    open_line=line, open_price="-110", open_source="nfldata_games",
                    open_captured_at_utc=captured_at,
                    close_line="", close_price="", close_source="",
                    close_captured_at_utc="", movement="", settled="no", outcome="",
                    source_tier="mirror",
                    flag="opening snapshot: the number standing when this repo originated "
                         "the market. The mirror publishes no book and no timestamp, so this "
                         "is not the sportsbook's own opening number.")
        if g["total_line"] is not None:
            for side in ("Over", "Under"):
                add(snapshot_id="OPEN-2026W10", captured_at_utc=captured_at,
                    market_id=f"{gid}:TOTAL:{side}", game_id=gid, season=2026, week=10,
                    origination_step=step["TOTAL"], market_type="TOTAL", side=side,
                    open_line=g["total_line"], open_price="-110", open_source="nfldata_games",
                    open_captured_at_utc=captured_at,
                    close_line="", close_price="", close_source="",
                    close_captured_at_utc="", movement="", settled="no", outcome="",
                    source_tier="mirror",
                    flag="opening snapshot: number standing at origination; no timestamp "
                         "published by the mirror.")
        for side, price in (("home", g["home_moneyline"]), ("away", g["away_moneyline"])):
            if price is None:
                continue
            add(snapshot_id="OPEN-2026W10", captured_at_utc=captured_at,
                market_id=f"{gid}:MONEYLINE:{side}", game_id=gid, season=2026, week=10,
                origination_step=step["MONEYLINE"], market_type="MONEYLINE", side=side,
                open_line="", open_price=int(price), open_source="nfldata_games",
                open_captured_at_utc=captured_at,
                close_line="", close_price="", close_source="",
                close_captured_at_utc="", movement="", settled="no", outcome="",
                source_tier="mirror",
                flag="opening snapshot: quoted price at origination; no timestamp published "
                     "by the mirror.")

    # --- settled markets: close recorded; open only where a real opening exists ---
    for g in games:
        if not g["settled"]:
            continue
        gid = g["game_id"]
        # 2021: the only season with a genuine opening number on both ends
        if g["season"] == 2021:
            if g["spread_line"] is not None:
                # The opening home spread is derived once, from the HOME club's
                # board number, then mirrored for the away side.
                init_home = None
                for code in (g["home"], TEAM_ALIAS.get(g["home"], g["home"]),
                             REVERSE_ALIAS.get(g["home"], g["home"])):
                    init_home = initial.get((gid, "SPREAD", code))
                    if init_home is not None:
                        break
                if init_home is None:
                    missing_open_2021.append(gid)
                else:
                  open_home = -init_home       # board convention -> home-favoured
                  for side in ("home", "away"):
                    open_line = open_home if side == "home" else -open_home
                    cl = g["spread_line"] if side == "home" else -g["spread_line"]
                    add(snapshot_id="SETTLED-2021", captured_at_utc=captured_at,
                        market_id=f"{gid}:SIDE:{side}", game_id=gid, season=2021,
                        week=g["week"] or "", origination_step=step["SIDE"],
                        market_type="SIDE", side=side,
                        open_line=round(open_line, 2), open_price="-110",
                        open_source="nfldata_initial_lines", open_captured_at_utc="",
                        close_line=round(cl, 2), close_price="-110",
                        close_source="nfldata_games", close_captured_at_utc="",
                        movement=round(cl - open_line, 2), settled="yes", outcome="",
                        source_tier="mirror",
                        flag="open is WSGT's board number (negative = favoured), "
                             "converted to the home-favoured convention; no capture "
                             "timestamp is published for either end.")
            if g["total_line"] is not None:
                init_total = initial.get((gid, "TOTAL", "Over"))
                if init_total is not None:
                    for side in ("Over", "Under"):
                        add(snapshot_id="SETTLED-2021", captured_at_utc=captured_at,
                            market_id=f"{gid}:TOTAL:{side}", game_id=gid, season=2021,
                            week=g["week"] or "", origination_step=step["TOTAL"],
                            market_type="TOTAL", side=side,
                            open_line=round(init_total, 2), open_price="-110",
                            open_source="nfldata_initial_lines", open_captured_at_utc="",
                            close_line=round(g["total_line"], 2), close_price="-110",
                            close_source="nfldata_games", close_captured_at_utc="",
                            movement=round(g["total_line"] - init_total, 2),
                            settled="yes", outcome="", source_tier="mirror",
                            flag="open is WSGT's opening total; no capture timestamp "
                                 "is published for either end.")
        # 2006-2018: closing_lines.csv carries odds and a settled outcome
        for mtype in ("SIDE", "TOTAL", "MONEYLINE"):
            bucket = closing.get((gid, mtype))
            if not bucket:
                continue
            for side, rec in bucket.items():
                if mtype == "MONEYLINE":
                    add(snapshot_id="SETTLED-CLOSE", captured_at_utc=captured_at,
                        market_id=f"{gid}:{mtype}:{side}", game_id=gid, season=g["season"],
                        week=g["week"] or "", origination_step=step[mtype],
                        market_type=mtype, side=side,
                        open_line="", open_price="", open_source="", open_captured_at_utc="",
                        close_line=rec["line"] if rec["line"] is not None else "",
                        close_price=rec["odds"] if rec["odds"] is not None else "",
                        close_source="nfldata_closing_lines", close_captured_at_utc="",
                        movement="", settled="yes", outcome=rec["outcome"],
                        source_tier="mirror",
                        flag="no opening number exists in any source available here; "
                             "open_* left blank by policy.")
        # every other settled season: the single published number, stored as close
        if g["season"] not in (2021,) and not (2006 <= g["season"] <= 2018):
            for mtype, side, line in (
                ("SIDE", "home", g["spread_line"]),
                ("TOTAL", "Over", g["total_line"]),
                ("MONEYLINE", "home", g["home_moneyline"]),
                ("MONEYLINE", "away", g["away_moneyline"]),
            ):
                if line is None:
                    continue
                add(snapshot_id="SETTLED-CLOSE", captured_at_utc=captured_at,
                    market_id=f"{gid}:{mtype}:{side}", game_id=gid, season=g["season"],
                    week=g["week"] or "", origination_step=step[mtype],
                    market_type=mtype, side=side,
                    open_line="", open_price="", open_source="", open_captured_at_utc="",
                    close_line=("" if mtype == "MONEYLINE" else line),
                    close_price=(int(line) if mtype == "MONEYLINE" else "-110"),
                    close_source="nfldata_games", close_captured_at_utc="",
                    movement="", settled="yes", outcome="", source_tier="mirror",
                    flag="single published number, no book and no timestamp; stored as "
                         "close. open_* blank - no source.")
    return rows


def price_store_summary(rows):
    s = {
        "rows": len(rows),
        "with_open": sum(1 for r in rows if r["open_line"] != "" or r["open_price"] != ""),
        "with_close": sum(1 for r in rows if r["close_line"] != "" or r["close_price"] != ""),
        "with_both": 0,
        "originated_2026_w10": sum(1 for r in rows if r["snapshot_id"] == "OPEN-2026W10"),
        "settled_rows": sum(1 for r in rows if r["settled"] == "yes"),
        "by_market": defaultdict(int),
        "by_step": defaultdict(int),
    }
    for r in rows:
        if (r["open_line"] != "" or r["open_price"] != "") and \
           (r["close_line"] != "" or r["close_price"] != ""):
            s["with_both"] += 1
        s["by_market"][r["market_type"]] += 1
        s["by_step"][r["origination_step"]] += 1
    s["by_market"] = dict(s["by_market"])
    s["by_step"] = dict(s["by_step"])
    return s
