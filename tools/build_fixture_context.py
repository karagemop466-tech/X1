#!/usr/bin/env python3
"""Fixture context for the 2026 slate, built only from facts the league publishes.

    python3 tools/build_fixture_context.py           # write the store
    python3 tools/build_fixture_context.py --check   # fail if the committed files are stale

The brief asks for "a fixture-context feature set built only from published schedule facts". The
gate on that requirement is that *every* feature traces to a schedule field the league prints, so
each column below names its field and its file, and anything the page does not print is left blank
with a reason rather than filled from knowledge.

Inputs (all already verified in this repository; this builder re-reads no page):
  data/verification/2026_11_18/week11_slate_2026-11-18.tsv   Week 11 fixtures and byes, as read
  data/console/w10_finals_2026_11_17.csv                     Week 10 dates, notes, game centres
  data/console/schedule_week10.csv                           Week 10 kickoff slots, networks
  data/nfl/venues_2026_week10.csv                             per-fixture venues, from the game centre
  data/results/verified_results_2026.csv                     weeks 1-10 fixture dates, for rest days

Features
  kickoff_date / kickoff_time_as_printed / kickoff_utc  date and slot as printed; UTC conversion uses
                                                        a fixed EST offset (November, no DST change)
  day_of_week                                             derived from the printed date
  prime_time_slot                                         the block heading the game sits under
  network                                                 the broadcaster the page prints
  venue_as_printed                                        blank unless a page printed it (Week 10
                                                        from the game centre, Week 11 only for the
                                                        international fixture)
  rest_days / rest_hours                                  printed date difference against the club's
                                                        previous fixture in the same season
  short_week                                              rest_days <= 4
  came_off_bye                                            no fixture in the immediately previous week
  back_to_back_prime                                      prime-time last week and prime-time this week
  international                                           the printed venue/event is outside the US
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
OUT = os.path.join(D, "fixtures")

# Join-only aliases. The Week 11 page prints AZ in each club's logo URL, the repository's Week 10
# finals file prints ARZ; the Rams print LA on the schedule page and LAR in some captures.
CLUB_ALIAS = {"ARZ": "AZ", "LAR": "LA"}
US_STATES = re.compile(r",\s*(?:A[LKZR]|C[AOT]|D[EC]|F[LM]|G[AU]|H[IU]|I[DLN]|K[SAY]|MA|MD|M[ES]|"
                       r"M[NI]|N[CHJYZ]|O[HK]|P[AR]|RI|S[CD]|T[NX]|UT|V[AT]|W[AIVY])\b", re.I)
PRIME = {"Thursday Night Football": "TNF", "Sunday Night Football": "SNF",
         "Monday Night Football": "MNF"}
ET_OFFSET_H = 5
MAX_LOOKBACK_WEEKS = 4


def names_from_matchup(text: str) -> frozenset:
    """"Minnesota Vikings vs. San Francisco 49ers" -> {vikings, 49ers}.

    The last word of each side is the club name in every NFL matchup string, so the two official
    pages that name fixtures differently (the international list by full name, the schedule page by
    game-centre slug) can be joined without a hand-written team table."""
    parts = re.split(r"\s+vs\.?\s+", text or "")
    out = set()
    for part in parts:
        words = re.findall(r"[A-Za-z0-9]+", part)
        if words:
            out.add(words[-1].lower())
    return frozenset(out)


def names_from_slug(slug: str) -> frozenset:
    """"vikings-at-49ers-2026-reg-11" -> {vikings, 49ers}."""
    core = re.sub(r"-\d{4}-(?:reg|pre|post)-\d+$", "", (slug or "").strip("/").split("/")[-1])
    parts = re.split(r"-at-", core)
    return frozenset(p.split("-")[-1].lower() for p in parts if p)


def _alias(code: str) -> str:
    code = (code or "").strip().upper()
    return CLUB_ALIAS.get(code, code)


def read_tsv(path):
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def load_inputs():
    """The Week 11 read file holds two tables with different headers: the slate, then the bye block.
    They are parsed as two tables rather than forced through one header, because a bye row is not a
    game row and a shared header would silently invent columns for it."""
    games, byes = [], []
    mode = None
    header = None
    with open(os.path.join(D, "verification", "2026_11_18", "week11_slate_2026-11-18.tsv"),
              encoding="utf-8") as fh:
        for ln in fh.read().split("\n"):
            if not ln.strip():
                continue
            if ln.lstrip().startswith("#"):
                continue
            cells = ln.split("\t")
            if cells[0] == "seq":
                header, mode = cells, "games"
                continue
            if cells[0] == "club":
                header, mode = cells, "byes"
                continue
            rec = dict(zip(header, cells))
            (games if mode == "games" else byes).append(rec)
    intl = {}
    ip = os.path.join(D, "nfl", "international_2026.csv")
    if os.path.exists(ip):
        for r in csv.DictReader(open(ip, encoding="utf-8")):
            wk = (r.get("week") or "").strip()
            if not wk:
                continue
            slug = (r.get("matchup") or "").strip()
            key = (r.get("date", "").strip(), names_from_matchup(slug))
            if len(key[1]) == 2:
                intl[key] = r
    w10_byes = []
    bp = os.path.join(D, "nfl", "week10_byes.csv")
    if os.path.exists(bp):
        w10_byes = [_alias(r["team"]) for r in csv.DictReader(open(bp, encoding="utf-8"))
                    if (r.get("week") or "").strip() == "10"]
    w10_finals = list(csv.DictReader(open(os.path.join(D, "console", "w10_finals_2026_11_17.csv"),
                                          encoding="utf-8")))
    w10_sched = {r["GAMEID"].replace("-2026-reg-10", ""): r
                 for r in csv.DictReader(open(os.path.join(D, "console", "schedule_week10.csv"),
                                              encoding="utf-8"))}
    venues = {}
    vp = os.path.join(D, "nfl", "venues_2026_week10.csv")
    if os.path.exists(vp):
        for r in csv.DictReader(open(vp, encoding="utf-8")):
            venues[_alias(r["home"])] = r
    prior = []
    for r in csv.DictReader(open(os.path.join(D, "results", "verified_results_2026.csv"),
                                encoding="utf-8")):
        d = r.get("date_iso", "")
        if not d:
            continue
        try:
            day = dt.date.fromisoformat(d)
        except ValueError:
            continue
        for club, slot, opp in ((_alias(r["away_team"]), "away", _alias(r["home_team"])),
                               (_alias(r["home_team"]), "home", _alias(r["away_team"]))):
            prior.append(dict(week=int(r["week"]), club=club, opponent=opp, day=day,
                              game_id=r["game_id"], url=r.get("game_url", "")))
    for r in w10_finals:
        day = dt.date.fromisoformat(r["date_et"])
        slot = PRIME.get(r["note"], "")
        for club, opp in ((_alias(r["away"]), _alias(r["home"])), (_alias(r["home"]), _alias(r["away"]))):
            prior.append(dict(week=10, club=club, slot="n/a", opponent=opp, day=day,
                              game_id=r["game_id"], url=r.get("game_url", ""), prime=slot))
    return games, byes, w10_finals, w10_sched, venues, prior, intl, w10_byes


def kickoff_utc(date_str, time_str):
    if not date_str or not time_str:
        return None
    try:
        t = dt.datetime.strptime(time_str.replace(" ", ""), "%I:%M%p")
        d0 = dt.datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None
    naive = d0.replace(hour=t.hour, minute=t.minute)
    return (naive + dt.timedelta(hours=ET_OFFSET_H)).replace(tzinfo=dt.timezone.utc)


def previous(prior, club, before_week, before_day):
    """Most recent earlier fixture for this club, and whether the week before was a bye."""
    cands = [p for p in prior if p["club"] == club and p["week"] < before_week
             and p["day"] < before_day]
    if not cands:
        cands = [p for p in prior if p["club"] == club and p["day"] < before_day]
    cands.sort(key=lambda p: (p["day"], p["week"]))
    if not cands:
        return None, None
    p = cands[-1]
    bye_last = (before_week - p["week"]) > 1
    return p, bye_last


def build():
    (games, byes, w10_finals, w10_sched, venues, prior,
     intl, w10_byes) = load_inputs()
    rows = []

    # ---- Week 11: the slate read on 2026-11-18 ------------------------------
    for g in games:
        ko_day = dt.date.fromisoformat(g["kickoff_date_local"])
        ko_utc = kickoff_utc(g["kickoff_date_local"], g["kickoff_time_local"])
        slot = PRIME.get((g.get("game_slot") or "").strip(), "")
        net = (g.get("network") or "").strip()
        slug = g["game_url"].rstrip("/").split("/")[-1]
        i = intl.get((g["kickoff_date_local"], names_from_slug(slug)))
        printed = (g.get("venue_as_printed") or "").strip()
        venue = (i or {}).get("venue", "").strip() or printed
        v_src = (i or {}).get("source", "").strip() or g["source_url"]
        if i:
            note = "venue from the league's international-games list; the by-week page prints an event block only"
        elif printed:
            note = "event label as printed on the by-week page; no stadium name printed"
        else:
            note = "venue blank on the by-week page - R-24: read each game centre"
        for club, opp, side in ((_alias(g["away"]), _alias(g["home"]), "away"),
                               (_alias(g["home"]), _alias(g["away"]), "home")):
            p, bye_last = previous(prior, club, 11, ko_day)
            rest = (ko_day - p["day"]).days if p else None
            rows.append(dict(
                week=11, club=club, status_this_week="game", side=side,
                matchup=f'{_alias(g["away"])} at {_alias(g["home"])}', opponent=opp,
                kickoff_date=g["kickoff_date_local"], kickoff_time_as_printed=g["kickoff_time_local"],
                kickoff_utc=ko_utc.strftime("%Y-%m-%dT%H:%MZ") if ko_utc else "",
                day_of_week=ko_day.strftime("%A"), prime_time_slot=slot, network=net,
                venue_as_printed=venue,
                venue_source=v_src if venue else "no source: the by-week page prints no venue for this fixture",
                prior_fixture=p["game_id"] if p else "",
                prior_fixture_date=p["day"].isoformat() if p else "",
                rest_days=rest if rest is not None else "",
                rest_hours=(round((ko_utc - dt.datetime.combine(p["day"], dt.time(0),
                                                                tzinfo=dt.timezone.utc)
                                   ).total_seconds() / 3600) if p and ko_utc else ""),
                rest_basis=("printed kickoff date minus the club's previous printed fixture date"
                            if p else "no earlier fixture date in this repository"),
                short_week=("yes" if rest is not None and rest <= 4 else "no"
                            if rest is not None else ""),
                came_off_bye=("yes" if bye_last else "no" if p else ""),
                back_to_back_prime="unmeasured",
                international=("yes" if i else
                              "no" if US_STATES.search((i or {}).get("venue", "") + " " + printed) else ""),
                source_url=g["source_url"], game_url=g["game_url"],
                flags=(note + ("; kickoff converted with a fixed EST offset" if ko_utc else
                               "; no kickoff time printed")),
            ))

    # ---- Week 10: the completed slate, from verified reads -------------------
    for f in w10_finals:
        slug = f["game_url"].rstrip("/").split("/")[-1].replace("-2026-reg-10", "")
        s = w10_sched.get(slug, {})
        ko_day = dt.date.fromisoformat(f["date_et"])
        ko_utc = kickoff_utc(f["date_et"], s.get("KICKOFF_ET", ""))
        slot = PRIME.get((f.get("note") or "").strip(), "")
        v = venues.get(_alias(f["home"])) or {}
        venue = (v.get("stadium_as_printed") or "").strip().title()
        loc = (v.get("location_as_printed") or "").strip()
        slug10 = f["game_url"].rstrip("/").split("/")[-1]
        i = intl.get((f["date_et"], names_from_slug(slug10)))
        for club, opp, side in ((_alias(f["away"]), _alias(f["home"]), "away"),
                               (_alias(f["home"]), _alias(f["away"]), "home")):
            p, bye_last = previous(prior, club, 10, ko_day)
            rest = (ko_day - p["day"]).days if p else None
            rows.append(dict(
                week=10, club=club, status_this_week="game", side=side,
                matchup=f'{_alias(f["away"])} at {_alias(f["home"])}', opponent=opp,
                kickoff_date=f["date_et"], kickoff_time_as_printed=s.get("KICKOFF_ET", ""),
                kickoff_utc=ko_utc.strftime("%Y-%m-%dT%H:%MZ") if ko_utc else "",
                day_of_week=ko_day.strftime("%A"), prime_time_slot=slot,
                network=s.get("NETWORK", ""), venue_as_printed=venue,
                venue_source=v.get("game_center_url", "") or "no source",
                prior_fixture=p["game_id"] if p else "",
                prior_fixture_date=p["day"].isoformat() if p else "",
                rest_days=rest if rest is not None else "",
                rest_hours=(round((ko_utc - dt.datetime.combine(p["day"], dt.time(0),
                                                                tzinfo=dt.timezone.utc)
                                   ).total_seconds() / 3600) if p and ko_utc else ""),
                rest_basis=("printed kickoff date minus the club's previous printed fixture date"
                            if p else "no earlier fixture date in this repository"),
                short_week=("yes" if rest is not None and rest <= 4 else "no"
                            if rest is not None else ""),
                came_off_bye=("yes" if bye_last else "no" if p else ""),
                back_to_back_prime="unmeasured",
                international=("yes" if i else
                               "no" if venue and US_STATES.search(loc) else ""),
                source_url=f["source_url"], game_url=f["game_url"],
                flags=("venue blank in the Week 10 schedule row; read from the game centre"
                       if venue else "no venue read for this fixture"),
            ))

    # ---- Week 11 byes -------------------------------------------------------
    for b in byes:
        club = _alias(b["club"])
        p, bye_last = previous(prior, club, 11, dt.date(2026, 11, 19))
        rows.append(dict(
            week=11, club=club, status_this_week="bye", side="bye", matchup="bye",
            opponent="", kickoff_date="", kickoff_time_as_printed="", kickoff_utc="",
            day_of_week="", prime_time_slot="", network="", venue_as_printed="",
            venue_source="no fixture this week",
            prior_fixture=p["game_id"] if p else "", prior_fixture_date=p["day"].isoformat() if p else "",
            rest_days="", rest_hours="",
            rest_basis="no Week 11 fixture; rest to the next fixture is not read in this pack",
            short_week="", came_off_bye="", back_to_back_prime="", international="",
            source_url="https://www.nfl.com/schedules/2026/by-week/week-11", game_url="",
            flags=(f'bye as printed, with the record the same block prints ({b["record_on_page"]})'
                   f'; club code on the page: {b["logo_abbr_on_page"]}'),
        ))

    # ---- Week 10 byes -------------------------------------------------------
    # The by-week read that produced the Week 11 bye block was taken after Week 10 closed, so the
    # Week 10 bye clubs are the four the repository's Week 10 bye file names. That file carries no
    # per-row URL, so these rows publish a source marker rather than a link, and their records are
    # deliberately blank: the numbers in that file were not re-read against a page in this round.
    for club in sorted(w10_byes):
        p10, bye_last10 = previous(prior, club, 10, dt.date(2026, 11, 12))
        rows.append(dict(
            week=10, club=club, status_this_week="bye", side="bye", matchup="bye",
            opponent="", kickoff_date="", kickoff_time_as_printed="", kickoff_utc="",
            day_of_week="", prime_time_slot="", network="", venue_as_printed="",
            venue_source="no fixture this week", venue_location_as_printed="",
            prior_fixture=p10["game_id"] if p10 else "",
            prior_fixture_date=p10["day"].isoformat() if p10 else "",
            rest_days="", rest_hours="",
            rest_basis="no Week 10 fixture; rest to the next fixture is not read in this pack",
            short_week="", came_off_bye="", back_to_back_prime="", international="",
            source_url="", game_url="",
            flags=("bye week; the club list comes from data/nfl/week10_byes.csv, which carries no "
                   "per-row URL - records left blank because they were not re-read this round"),
        ))

    rows.sort(key=lambda r: (r["week"], r["matchup"], r["side"]))
    games_rows = [r for r in rows if r["status_this_week"] == "game"]
    w11 = [r for r in rows if r["week"] == 11]
    w10 = [r for r in rows if r["week"] == 10]
    rest_dist = {}
    for r in games_rows:
        if r["rest_days"] != "":
            rest_dist[r["rest_days"]] = rest_dist.get(r["rest_days"], 0) + 1
    summary = dict(
        dataset="fixture_context",
        title="Fixture context from published schedule facts only (Weeks 10-11, 2026)",
        generated_by="tools/build_fixture_context.py",
        read_of_record=dict(
            url="https://www.nfl.com/schedules/2026/by-week/week-11",
            read_utc="2026-11-18T03:05Z", method="rendered read, chunks 0-1 of 2",
            retained="data/verification/2026_11_18/week11_slate_2026-11-18.tsv"),
        rule=("A feature is published only when the field it traces to is printed on the page named "
              "in that row's source columns. Blank means the league printed nothing, and the row says "
              "so; nothing is filled from memory."),
        counts=dict(rows=len(rows), week11_rows=len(w11), week10_rows=len(w10),
                    clubs_covered_week10=len({r["club"] for r in w10}),
                    fixtures_week11=len([r for r in w11 if r["status_this_week"] == "game"]) // 2,
                    byes_week11=len([r for r in w11 if r["status_this_week"] == "bye"]),
                    byes_week10=len([r for r in w10 if r["status_this_week"] == "bye"]),
                    clubs_covered_week11=len({r["club"] for r in w11}),
                    with_venue_week10=len({r["matchup"] for r in w10 if r["venue_as_printed"]}),
                    with_venue_week11=len({r["matchup"] for r in w11 if r["venue_as_printed"]}),
                    with_rest_days=len([r for r in games_rows if r["rest_days"] != ""]),
                    short_week=len([r for r in games_rows if r["short_week"] == "yes"]),
                    came_off_bye=len([r for r in games_rows if r["came_off_bye"] == "yes"]),
                    prime_time_games=len([r for r in games_rows if r["prime_time_slot"]]),
                    international=len([r for r in games_rows if r["international"] == "yes"])),
        rest_days_distribution={str(k): v for k, v in sorted(rest_dist.items())},
        definitions=dict(
            rest_days="printed kickoff date minus the club's previous printed fixture date, in days",
            short_week="rest_days <= 4 (the Thursday-night pattern this feature exists to catch)",
            came_off_bye="no fixture in the immediately previous week",
            prime_time_slot="the block heading the fixture sits under on the schedule page",
            rest_hours=("approximate: measured to midnight UTC of the previous fixture date, because "
                        "weeks 1-9 are recorded as dates, so the value carries up to a day of slack"),
            international="the printed venue/event label is not a US state address",
            kickoff_utc=f"printed ET slot + {ET_OFFSET_H} h (EST, no DST in November 2026)",
        ),
        caveats=[
            "Week 11 venues are blank for 12 of 13 fixtures: the by-week page prints a location only "
            "for the international fixture. Per-fixture venues require the game-centre pass that "
            "data/nfl/venues_2026_week10.csv exists for in Week 10 (R-24, PARTIAL).",
            "Kickoff times are read from the rendered page in its default (Eastern) presentation; the "
            "page's LOCAL toggle was not exercised, so a reader in another zone sees different strings "
            "for the same instant.",
            "rest_days is a date difference, not a game-clock difference, because weeks 1-9 fixtures "
            "are recorded with a date and not a printed slot in this repository.",
            "back_to_back_prime is published as 'unmeasured' on every row: the Week 10 finals file "
            "carries a prime-time note for 3 of 14 games and the weeks 1-9 reads print none, so the "
            "feature would be built on a partial field. The field is kept in the schema so a reader "
            "can see that it was measured as unavailable, not forgotten.",
        ],
        alias_table=[dict(from_code=k, to_code=v) for k, v in sorted(CLUB_ALIAS.items())],
    )
    return rows, summary


COLS = ["week", "club", "status_this_week", "side", "matchup", "opponent", "kickoff_date",
        "kickoff_time_as_printed", "kickoff_utc", "day_of_week", "prime_time_slot", "network",
        "venue_as_printed", "venue_source", "prior_fixture", "prior_fixture_date", "rest_days",
        "rest_hours", "rest_basis", "short_week", "came_off_bye", "back_to_back_prime",
        "international", "source_url", "game_url", "flags"]


def write(rows, summary, check=False):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLS)
    for r in rows:
        w.writerow([r.get(c, "") for c in COLS])
    files = {"fixture_context_2026.csv": buf.getvalue(),
             "summary.json": json.dumps(summary, indent=1) + "\n"}
    if check:
        bad = [n for n, t in files.items()
               if not os.path.exists(os.path.join(OUT, n))
               or open(os.path.join(OUT, n), encoding="utf-8").read() != t]
        if bad:
            print("[fixture-context] STALE: " + ", ".join(bad))
            return 1
        print(f"[fixture-context] current: {len(rows)} rows")
        return 0
    os.makedirs(OUT, exist_ok=True)
    for n, t in files.items():
        with open(os.path.join(OUT, n), "w", encoding="utf-8") as fh:
            fh.write(t)
    c = summary["counts"]
    print(f"[fixture-context] wrote {len(rows)} rows: {c['week11_rows']} for Week 11 "
          f"({c['with_venue_week11']} with a printed venue), {c['week10_rows']} for Week 10 "
          f"({c['with_venue_week10']} with a venue)")
    return 0


if __name__ == "__main__":
    sys.exit(write(*build(), check="--check" in sys.argv))
