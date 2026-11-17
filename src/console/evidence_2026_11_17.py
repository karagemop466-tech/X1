#!/usr/bin/env python3
"""Dated official reads taken on 2026-11-17, and what they say about the published tables.

Why this module exists
----------------------
The console's standings page claimed that all 32 clubs x 16 fields had been "re-read from
the league's own standings table on the build date" and matched with no mismatches. That
claim was not reproducible: the compared numbers were a literal constant
(``STANDINGS_RECHECK``) and the table actually audited was
``data/verify/official_standings_2026_w10.psv``, a transcription dated 2026-11-14 that
covers the 137 games played through the Week 10 Thursday game.

This module holds one dated read, transcribed from the official pages on **2026-11-17
(UTC)**, with the URL and the clock time recorded next to every row. It does three things
and nothing else:

1. **Stores the read.** ``STANDINGS_2026_11_17``, ``WEEK10_FINALS_2026_11_17`` and
   ``BYES_WEEK11`` are literal transcriptions. No value is computed, inferred or copied
   from the repository's own tables.
2. **Diffs it against what is published** — the 2026-11-14 PSV transcription, the
   collector's payload (``data/pipeline/*.json``), and the mirror's games table — and
   reports every cell that disagrees. Two independent extraction paths (this read and the
   collector's parser) agreeing is what promotes a cell from "unverified" to "verified".
3. **Says what it cannot support.** The regression facts the console would need before
   its 2026 numbers can be called current — which 2026 rows carry a knockout price, and
   whether the mirror behind the results feed has published the Week 10 finals — are
   *measured* here, not assumed.

Nothing in this module is used to overwrite a published value. A disagreement is published
as a disagreement, because the value that is wrong is the claim, not the newest number.
"""
from __future__ import annotations

import csv
import os
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# provenance for this read
# ---------------------------------------------------------------------------
READ_UTC = "2026-11-17T22:46Z"
READ_METHOD = (
    "Direct read of the official page, transcribed by hand row by row, then machine-diffed "
    "against the collector payload (data/pipeline/*.json, read 2026-11-17T19:49Z) and the "
    "2026-11-14 PSV transcription already in the repository. Where this read and the "
    "collector's parser agree, the cell is double-entered; where they disagree, the cell is "
    "flagged and neither value is published as verified."
)
STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"
SCHEDULE_URL = "https://www.nfl.com/schedules/2026/REG/week/10"
WEEK11_URL = "https://www.nfl.com/schedules/2026/REG/week/11"

# Columns exactly as the transcribed PSV prints them, so a cell-by-cell diff needs no
# mapping table. PCT/NET are derived by the league's page and are transcribed, not computed.
STANDINGS_COLS = ["TEAM", "W", "L", "T", "PCT", "PF", "PA", "NET", "HOME", "ROAD",
                  "DIV", "DIVPCT", "CONF", "CONFPCT", "NONCONF", "STRK", "LAST5"]

# fmt: off
# 32 rows, read off https://www.nfl.com/standings/league/2026/REG on 2026-11-17 (UTC).
# Order is the page's own order (league view, best record first), preserved rather than
# re-sorted, because the order is itself evidence that the page was read and not rebuilt.
STANDINGS_2026_11_17: List[Dict[str, str]] = [
    dict(TEAM="BUF", W="8",  L="1",  T="0", PCT="0.889", PF="287", PA="199", NET="88",
         HOME="3-1-0",   ROAD="5-0-0", DIV="1-1-0", DIVPCT="0.500", CONF="5-1-0",
         CONFPCT="0.833", NONCONF="3-0-0", STRK="5W", LAST5="5-0-0"),
    dict(TEAM="SF",  W="8",  L="1",  T="0", PCT="0.889", PF="281", PA="196", NET="85",
         HOME="5-0-0",   ROAD="3-1-0", DIV="3-0-0", DIVPCT="1.000", CONF="5-1-0",
         CONFPCT="0.833", NONCONF="3-0-0", STRK="2W", LAST5="4-1-0"),
    dict(TEAM="CHI", W="7",  L="2",  T="0", PCT="0.778", PF="241", PA="184", NET="57",
         HOME="4-1-0",   ROAD="3-1-0", DIV="0-2-0", DIVPCT="0.000", CONF="5-2-0",
         CONFPCT="0.714", NONCONF="2-0-0", STRK="4W", LAST5="4-1-0"),
    dict(TEAM="CIN", W="7",  L="2",  T="0", PCT="0.778", PF="278", PA="193", NET="85",
         HOME="3-1-0",   ROAD="4-1-0", DIV="2-1-0", DIVPCT="0.667", CONF="5-2-0",
         CONFPCT="0.714", NONCONF="2-0-0", STRK="5W", LAST5="5-0-0"),
    dict(TEAM="DEN", W="7",  L="2",  T="0", PCT="0.778", PF="198", PA="186", NET="12",
         HOME="4-0-0",   ROAD="3-2-0", DIV="2-1-0", DIVPCT="0.667", CONF="3-1-0",
         CONFPCT="0.750", NONCONF="4-1-0", STRK="5W", LAST5="5-0-0"),
    dict(TEAM="DET", W="7",  L="2",  T="0", PCT="0.778", PF="257", PA="199", NET="58",
         HOME="5-0-0",   ROAD="2-2-0", DIV="2-0-0", DIVPCT="1.000", CONF="4-1-0",
         CONFPCT="0.800", NONCONF="3-1-0", STRK="5W", LAST5="5-0-0"),
    dict(TEAM="JAX", W="7",  L="2",  T="0", PCT="0.778", PF="269", PA="144", NET="125",
         HOME="4-1-0",   ROAD="3-1-0", DIV="2-1-0", DIVPCT="0.667", CONF="6-2-0",
         CONFPCT="0.750", NONCONF="1-0-0", STRK="3W", LAST5="4-1-0"),
    dict(TEAM="KC",  W="7",  L="2",  T="0", PCT="0.778", PF="237", PA="156", NET="81",
         HOME="4-0-0",   ROAD="3-2-0", DIV="3-1-0", DIVPCT="0.750", CONF="6-1-0",
         CONFPCT="0.857", NONCONF="1-1-0", STRK="2W", LAST5="3-2-0"),
    dict(TEAM="MIN", W="7",  L="2",  T="0", PCT="0.778", PF="176", PA="126", NET="50",
         HOME="3-1-0",   ROAD="4-1-0", DIV="3-1-0", DIVPCT="0.750", CONF="5-1-0",
         CONFPCT="0.833", NONCONF="2-1-0", STRK="1W", LAST5="3-2-0"),
    dict(TEAM="PIT", W="6",  L="3",  T="0", PCT="0.667", PF="198", PA="182", NET="16",
         HOME="4-0-0",   ROAD="2-3-0", DIV="2-2-0", DIVPCT="0.500", CONF="3-3-0",
         CONFPCT="0.500", NONCONF="3-0-0", STRK="1L", LAST5="4-1-0"),
    dict(TEAM="NYG", W="5",  L="3",  T="1", PCT="0.611", PF="203", PA="196", NET="7",
         HOME="3-2-0",   ROAD="2-1-1", DIV="2-1-1", DIVPCT="0.625", CONF="3-3-1",
         CONFPCT="0.500", NONCONF="2-0-0", STRK="1L", LAST5="2-2-1"),
    dict(TEAM="CLE", W="6",  L="4",  T="0", PCT="0.600", PF="188", PA="220", NET="-32",
         HOME="4-0-0",   ROAD="2-4-0", DIV="2-1-0", DIVPCT="0.667", CONF="4-3-0",
         CONFPCT="0.571", NONCONF="2-1-0", STRK="1W", LAST5="3-2-0"),
    dict(TEAM="GB",  W="6",  L="4",  T="0", PCT="0.600", PF="226", PA="221", NET="5",
         HOME="3-2-0",   ROAD="3-2-0", DIV="1-3-0", DIVPCT="0.250", CONF="4-4-0",
         CONFPCT="0.500", NONCONF="2-0-0", STRK="1L", LAST5="3-2-0"),
    dict(TEAM="LA",  W="6",  L="4",  T="0", PCT="0.600", PF="248", PA="187", NET="61",
         HOME="2-3-0",   ROAD="4-1-0", DIV="1-2-0", DIVPCT="0.333", CONF="4-2-0",
         CONFPCT="0.667", NONCONF="2-2-0", STRK="4W", LAST5="4-1-0"),
    dict(TEAM="SEA", W="6",  L="4",  T="0", PCT="0.600", PF="223", PA="175", NET="48",
         HOME="4-2-0",   ROAD="2-2-0", DIV="2-1-0", DIVPCT="0.667", CONF="2-3-0",
         CONFPCT="0.400", NONCONF="4-1-0", STRK="2W", LAST5="3-2-0"),
    dict(TEAM="NE",  W="5",  L="5",  T="0", PCT="0.500", PF="221", PA="242", NET="-21",
         HOME="3-1-0",   ROAD="2-4-0", DIV="3-0-0", DIVPCT="1.000", CONF="5-1-0",
         CONFPCT="0.833", NONCONF="0-4-0", STRK="2L", LAST5="2-3-0"),
    dict(TEAM="CAR", W="4",  L="5",  T="0", PCT="0.444", PF="219", PA="236", NET="-17",
         HOME="1-3-0",   ROAD="3-2-0", DIV="2-1-0", DIVPCT="0.667", CONF="4-3-0",
         CONFPCT="0.571", NONCONF="0-2-0", STRK="1W", LAST5="2-3-0"),
    dict(TEAM="BAL", W="4",  L="6",  T="0", PCT="0.400", PF="209", PA="259", NET="-50",
         HOME="1-4-0",   ROAD="3-2-0", DIV="0-2-0", DIVPCT="0.000", CONF="2-5-0",
         CONFPCT="0.286", NONCONF="2-1-0", STRK="5L", LAST5="0-5-0"),
    dict(TEAM="DAL", W="4",  L="6",  T="0", PCT="0.400", PF="286", PA="282", NET="4",
         HOME="1-4-0",   ROAD="3-2-0", DIV="2-1-0", DIVPCT="0.667", CONF="2-5-0",
         CONFPCT="0.286", NONCONF="2-1-0", STRK="1L", LAST5="2-3-0"),
    dict(TEAM="LV",  W="4",  L="6",  T="0", PCT="0.400", PF="251", PA="289", NET="-38",
         HOME="1-4-0",   ROAD="3-2-0", DIV="1-1-0", DIVPCT="0.500", CONF="3-3-0",
         CONFPCT="0.500", NONCONF="1-3-0", STRK="2L", LAST5="1-4-0"),
    dict(TEAM="WAS", W="3",  L="5",  T="1", PCT="0.389", PF="196", PA="223", NET="-27",
         HOME="2-2-1",   ROAD="1-3-0", DIV="2-2-1", DIVPCT="0.500", CONF="3-4-1",
         CONFPCT="0.438", NONCONF="0-1-0", STRK="1W", LAST5="2-2-1"),
    dict(TEAM="HOU", W="3",  L="6",  T="0", PCT="0.333", PF="233", PA="219", NET="14",
         HOME="0-4-0",   ROAD="3-2-0", DIV="2-1-0", DIVPCT="0.667", CONF="3-4-0",
         CONFPCT="0.429", NONCONF="0-2-0", STRK="1L", LAST5="3-2-0"),
    dict(TEAM="NO",  W="3",  L="6",  T="0", PCT="0.333", PF="202", PA="236", NET="-34",
         HOME="1-5-0",   ROAD="2-1-0", DIV="0-2-0", DIVPCT="0.000", CONF="1-4-0",
         CONFPCT="0.200", NONCONF="2-2-0", STRK="1L", LAST5="2-3-0"),
    dict(TEAM="TB",  W="3",  L="6",  T="0", PCT="0.333", PF="202", PA="178", NET="24",
         HOME="1-4-0",   ROAD="2-2-0", DIV="2-0-0", DIVPCT="1.000", CONF="3-3-0",
         CONFPCT="0.500", NONCONF="0-3-0", STRK="1L", LAST5="3-2-0"),
    dict(TEAM="AZ",  W="3",  L="7",  T="0", PCT="0.300", PF="184", PA="289", NET="-105",
         HOME="0-4-0",   ROAD="3-3-0", DIV="1-4-0", DIVPCT="0.200", CONF="2-6-0",
         CONFPCT="0.250", NONCONF="1-1-0", STRK="2L", LAST5="2-3-0"),
    dict(TEAM="ATL", W="3",  L="7",  T="0", PCT="0.300", PF="201", PA="258", NET="-57",
         HOME="1-5-0",   ROAD="2-2-0", DIV="1-2-0", DIVPCT="0.333", CONF="3-3-0",
         CONFPCT="0.500", NONCONF="0-4-0", STRK="3L", LAST5="1-4-0"),
    dict(TEAM="IND", W="3",  L="7",  T="0", PCT="0.300", PF="208", PA="271", NET="-63",
         HOME="2-3-0",   ROAD="1-4-0", DIV="1-2-0", DIVPCT="0.333", CONF="2-5-0",
         CONFPCT="0.286", NONCONF="1-2-0", STRK="1W", LAST5="1-4-0"),
    dict(TEAM="PHI", W="2",  L="7",  T="0", PCT="0.222", PF="148", PA="221", NET="-73",
         HOME="1-4-0",   ROAD="1-3-0", DIV="1-3-0", DIVPCT="0.250", CONF="1-6-0",
         CONFPCT="0.143", NONCONF="1-1-0", STRK="7L", LAST5="0-5-0"),
    dict(TEAM="NYJ", W="2",  L="8",  T="0", PCT="0.200", PF="194", PA="254", NET="-60",
         HOME="1-4-0",   ROAD="1-4-0", DIV="0-3-0", DIVPCT="0.000", CONF="2-5-0",
         CONFPCT="0.286", NONCONF="0-3-0", STRK="5L", LAST5="0-5-0"),
    dict(TEAM="LAC", W="1",  L="8",  T="0", PCT="0.111", PF="144", PA="239", NET="-95",
         HOME="0-4-0",   ROAD="1-4-0", DIV="0-3-0", DIVPCT="0.000", CONF="1-5-0",
         CONFPCT="0.167", NONCONF="0-3-0", STRK="1W", LAST5="1-4-0"),
    dict(TEAM="MIA", W="1",  L="8",  T="0", PCT="0.111", PF="148", PA="224", NET="-76",
         HOME="0-4-0",   ROAD="1-4-0", DIV="1-1-0", DIVPCT="0.500", CONF="1-5-0",
         CONFPCT="0.167", NONCONF="0-3-0", STRK="3L", LAST5="1-4-0"),
    dict(TEAM="TEN", W="1",  L="8",  T="0", PCT="0.111", PF="167", PA="239", NET="-72",
         HOME="0-5-0",   ROAD="1-3-0", DIV="1-2-0", DIVPCT="0.333", CONF="1-6-0",
         CONFPCT="0.143", NONCONF="0-2-0", STRK="3L", LAST5="1-4-0"),
]

# Week 10 finals, read off https://www.nfl.com/schedules/2026/REG/week/10 on 2026-11-17 (UTC).
# Every one of the 14 games is FINAL. Scores are the league's printed score line; the
# winner is the league's own "Winner Indicator", not a comparison computed here.
#
# `in_2026_11_14_snapshot` records the one distinction that made the first run of the
# arithmetic below fail: the 2026-11-14 transcription was taken AFTER the Thursday game,
# so it already counts WAS-NYG. Adding all 14 finals to it double-counted that game and
# produced 6 false "mismatches" on WAS and NYG. The flag is set from the game date
# (2026-11-12, two days before the snapshot), not from a guess.
WEEK10_FINALS_2026_11_17: List[Dict[str, str]] = [
    dict(game_id="commanders-at-giants-2026-reg-10",  away="WAS", away_score="24",
         home="NYG", home_score="21", date_et="2026-11-12", window="Thursday Night Football",
         in_2026_11_14_snapshot="yes"),
    dict(game_id="patriots-at-lions-2026-reg-10",     away="NE",  away_score="10",
         home="DET", home_score="35", date_et="2026-11-15", window="International (Munich)",
         in_2026_11_14_snapshot="no"),
    dict(game_id="chiefs-at-falcons-2026-reg-10",     away="KC",  away_score="35",
         home="ATL", home_score="13", date_et="2026-11-15", window="Sunday 1:00 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="texans-at-browns-2026-reg-10",      away="HOU", away_score="24",
         home="CLE", home_score="27", date_et="2026-11-15", window="Sunday 1:00 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="vikings-at-packers-2026-reg-10",    away="MIN", away_score="30",
         home="GB",  home_score="10", date_et="2026-11-15", window="Sunday 1:00 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="dolphins-at-colts-2026-reg-10",     away="MIA", away_score="22",
         home="IND", home_score="24", date_et="2026-11-15", window="Sunday 1:00 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="panthers-at-saints-2026-reg-10",    away="CAR", away_score="20",
         home="NO",  home_score="17", date_et="2026-11-15", window="Sunday 1:00 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="bills-at-jets-2026-reg-10",         away="BUF", away_score="31",
         home="NYJ", home_score="12", date_et="2026-11-15", window="Sunday 1:00 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="jaguars-at-titans-2026-reg-10",     away="JAX", away_score="40",
         home="TEN", home_score="23", date_et="2026-11-15", window="Sunday 1:00 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="rams-at-cardinals-2026-reg-10",     away="LA",  away_score="34",
         home="AZ",  home_score="6",  date_et="2026-11-15", window="Sunday 4:05 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="seahawks-at-raiders-2026-reg-10",   away="SEA", away_score="21",
         home="LV",  home_score="13", date_et="2026-11-15", window="Sunday 4:05 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="49ers-at-cowboys-2026-reg-10",      away="SF",  away_score="46",
         home="DAL", home_score="40", date_et="2026-11-15", window="Sunday 4:25 PM",
         in_2026_11_14_snapshot="no"),
    dict(game_id="steelers-at-bengals-2026-reg-10",   away="PIT", away_score="18",
         home="CIN", home_score="38", date_et="2026-11-15", window="Sunday Night Football",
         in_2026_11_14_snapshot="no"),
    dict(game_id="chargers-at-ravens-2026-reg-10",    away="LAC", away_score="23",
         home="BAL", home_score="20", date_et="2026-11-16", window="Monday Night Football",
         in_2026_11_14_snapshot="no"),
]

# Week 10 byes, read off the same page's "Teams on Bye" block, with the record printed there.
BYES_WEEK10_2026_11_17: List[Tuple[str, str]] = [
    ("CHI", "7-2"), ("DEN", "7-2"), ("PHI", "2-7"), ("TB", "3-6"),
]
# fmt: on

# The games-played count implied by the league's own standings, not by a count of rows in
# this repository: every club's W+L+T summed gives two club-games per game played.
def games_played_from_standings(rows: List[Dict[str, str]]) -> int:
    total = sum(int(r["W"]) + int(r["L"]) + int(r["T"]) for r in rows)
    return total // 2


# ---------------------------------------------------------------------------
# comparison helpers
# ---------------------------------------------------------------------------

def read_psv(rel: str) -> List[Dict[str, str]]:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.startswith("#")]
    if not lines:
        return []
    head = lines[0].split("|")
    return [dict(zip(head, ln.split("|"))) for ln in lines[1:]]


def read_pipeline(name: str) -> List[Dict[str, str]]:
    import json
    path = os.path.join(ROOT, "data", "pipeline", name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("rows", [])


def _norm(v: str) -> str:
    """Normalise only presentation differences, never content.

    The collector prints split records as ``3 - 1 - 0``; the league's page prints
    ``3-1-0``. A diff that reported 192 "mismatches" for spacing would bury the real ones,
    so whitespace around the separators is collapsed. Nothing else is touched: a digit,
    a letter or a minus sign that differs is still a difference.
    """
    t = (v or "").strip()
    if t and all(ch in "0123456789- " for ch in t):
        t = "-".join(part.strip() for part in t.split("-"))
    return t


def compare_rows(latest: List[Dict[str, str]], other: List[Dict[str, str]],
                 key: str, fields: List[str], other_map: Optional[Dict[str, str]] = None,
                 other_key: Optional[str] = None) -> Tuple[int, int, List[Dict[str, str]]]:
    """Cell-by-cell diff. Returns (comparisons, matches, differences).

    A field present in ``latest`` but absent from ``other`` is counted as a comparison and
    a difference with ``other`` = "" — a column that disappeared is a finding, not a skip.
    """
    other_by = {r.get(other_key or key, ""): r for r in other}
    comp = match = 0
    diffs: List[Dict[str, str]] = []
    for row in latest:
        k = row[key]
        o = other_by.get(k)
        for f in fields:
            comp += 1
            mine = _norm(row.get(f) or "")
            theirs = "" if o is None else _norm(o.get(other_map.get(f, f) if other_map else f) or "")
            if o is None:
                diffs.append({"key": k, "field": f, "mine": mine, "other": "(row absent)"})
            elif mine == theirs:
                match += 1
            else:
                diffs.append({"key": k, "field": f, "mine": mine, "other": theirs})
    return comp, match, diffs


def note_club_mismatches(diffs: List[Dict[str, str]]) -> List[str]:
    return sorted({d["key"] for d in diffs})


def closure_checks(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """League-wide arithmetic on the transcribed read itself.

    A mis-transcribed row almost always breaks one of these, which is why they are applied
    to the *new* read before it is used to accuse anything older of being wrong.
    """
    out: List[Dict[str, str]] = []
    w = sum(int(r["W"]) for r in rows)
    l = sum(int(r["L"]) for r in rows)
    t = sum(int(r["T"]) for r in rows)
    pf = sum(int(r["PF"]) for r in rows)
    pa = sum(int(r["PA"]) for r in rows)
    net = sum(int(r["NET"]) for r in rows)
    out.append({"check": "wins == losses", "value": f"{w} vs {l}", "ok": str(w == l)})
    out.append({"check": "ties even", "value": str(t), "ok": str(t % 2 == 0)})
    out.append({"check": "points for == points against", "value": f"{pf} vs {pa}",
                "ok": str(pf == pa)})
    out.append({"check": "net points sum to zero", "value": str(net), "ok": str(net == 0)})
    # Per-club: W+L+T must equal PF/PA plausibility only in that a club plays one game per
    # W/L/T entry; PCT must equal (W + T/2) / (W + L + T) for every row the league prints.
    bad_pct = []
    for r in rows:
        played = int(r["W"]) + int(r["L"]) + int(r["T"])
        if played == 0:
            continue
        pct = (int(r["W"]) + 0.5 * int(r["T"])) / played
        if abs(round(pct, 3) - float(r["PCT"])) > 0.0011:
            bad_pct.append(f'{r["TEAM"]}: printed {r["PCT"]}, recomputed {pct:.3f}')
        if int(r["PF"]) - int(r["PA"]) != int(r["NET"]):
            bad_pct.append(f'{r["TEAM"]}: NET {r["NET"]} != PF-PA {int(r["PF"]) - int(r["PA"])}')
    out.append({"check": "PCT and NET recompute from the printed W/L/T/PF/PA",
                "value": "; ".join(bad_pct) or "all 32 rows", "ok": str(not bad_pct)})
    # Split records must add up to the record itself.
    splits = []
    for r in rows:
        played = int(r["W"]) + int(r["L"]) + int(r["T"])
        for grp in ("HOME", "ROAD"):
            parts = [int(x) for x in r[grp].split("-")]
            if sum(parts) == 0:
                continue
        h = [int(x) for x in r["HOME"].split("-")]
        rd = [int(x) for x in r["ROAD"].split("-")]
        if sum(h) + sum(rd) != played:
            splits.append(f'{r["TEAM"]}: home {sum(h)} + road {sum(rd)} != {played}')
        if h[0] + rd[0] != int(r["W"]) or h[1] + rd[1] != int(r["L"]) or h[2] + rd[2] != int(r["T"]):
            splits.append(f'{r["TEAM"]}: home+road record != W-L-T')
        n = [int(x) for x in r["NONCONF"].split("-")]
        c = [int(x) for x in r["CONF"].split("-")]
        if c[0] + n[0] != int(r["W"]) or c[1] + n[1] != int(r["L"]) or (\
                c[2] if len(c) > 2 else 0) + (n[2] if len(n) > 2 else 0) != int(r["T"]):
            splits.append(f'{r["TEAM"]}: conf+non-conf record != W-L-T')
        d = [int(x) for x in r["DIV"].split("-")]
        if d[0] > c[0] or d[1] > c[1]:
            splits.append(f'{r["TEAM"]}: division record exceeds conference record')
        if not (r["STRK"][:-1].isdigit() and r["STRK"][-1] in "WL"):
            splits.append(f'{r["TEAM"]}: streak {r["STRK"]!r} is not nW/nL')
        l5 = [int(x) for x in r["LAST5"].split("-")]
        if sum(l5) > min(5, played):
            splits.append(f'{r["TEAM"]}: last-5 sums to more games than played')
    out.append({"check": "home + road, conf + non-conf, div <= conf, streak and last-5 shapes",
                "value": "; ".join(splits) or "all 32 rows", "ok": str(not splits)})
    return out


def week10_scores_check() -> Dict[str, object]:
    """Do the 14 finals reproduce the league's own standings after Week 10?

    The standings are the official source; if adding the 14 scores to the 2026-11-14
    snapshot's table does not reproduce today's table for every club, then either a score
    or a standings row was misread. This is the arithmetic that lets one read vouch for
    the other, and it is why the two datasets are published together.
    """
    old = {r["TEAM"]: r for r in read_psv("data/verify/official_standings_2026_w10.psv")}
    new = {r["TEAM"]: r for r in STANDINGS_2026_11_17}
    delta = {}
    already = [g for g in WEEK10_FINALS_2026_11_17
               if g.get("in_2026_11_14_snapshot") == "yes"]
    for g in [g for g in WEEK10_FINALS_2026_11_17
              if g.get("in_2026_11_14_snapshot") != "yes"]:
        for club, mine, theirs in ((g["away"], int(g["away_score"]), int(g["home_score"])),
                                   (g["home"], int(g["home_score"]), int(g["away_score"]))):
            d = delta.setdefault(club, {"W": 0, "L": 0, "T": 0, "PF": 0, "PA": 0})
            d["PF"] += mine
            d["PA"] += theirs
            if mine > theirs:
                d["W"] += 1
            elif theirs > mine:
                d["L"] += 1
            else:
                d["T"] += 1
    checks = mismatches = 0
    detail = []
    for club, o in old.items():
        n = new.get(club)
        if n is None:
            mismatches += 1
            detail.append(f"{club}: absent from the new read")
            continue
        d = delta.get(club, {"W": 0, "L": 0, "T": 0, "PF": 0, "PA": 0})
        for f in ("W", "L", "T", "PF", "PA"):
            checks += 1
            want = int(o[f]) + d[f]
            got = int(n[f])
            if want != got:
                mismatches += 1
                detail.append(f"{club}.{f}: 2026-11-14 table {o[f]} + week 10 {d[f]} = {want}, "
                              f"league prints {got}")
    return {"clubs": len(old), "checks": checks, "mismatches": mismatches,
            "detail": detail[:40], "scores_games": len(WEEK10_FINALS_2026_11_17),
            "games_played_implied": games_played_from_standings(STANDINGS_2026_11_17)}


def published_vs_league() -> Dict[str, object]:
    """The published console table against today's league standings."""
    published = read_psv("data/verify/official_standings_2026_w10.psv")
    fields = ["W", "L", "T", "PCT", "PF", "PA", "NET", "HOME", "ROAD", "DIV", "DIVPCT",
              "CONF", "CONFPCT", "NONCONF", "STRK", "LAST5"]
    comp, match, diffs = compare_rows(STANDINGS_2026_11_17, published, "TEAM", fields)
    return {"comparisons": comp, "matches": match, "mismatches": len(diffs),
            "clubs": note_club_mismatches(diffs), "detail": diffs}


def collector_vs_league() -> Dict[str, object]:
    """The collector's payload (a second, independent extraction of the same page)."""
    rows = read_pipeline("standings.json")
    if not rows:
        return {"available": False, "comparisons": 0, "matches": 0, "mismatches": 0,
                "clubs": [], "detail": []}
    other_map = {"TEAM": "team_abbrev", "W": "W", "L": "L", "T": "T", "PCT": "PCT", "PF": "PF",
                 "PA": "PA", "NET": "NET_PTS", "HOME": "HOME", "ROAD": "ROAD", "DIV": "DIV",
                 "DIVPCT": "DIV_PCT", "CONF": "CONF", "CONFPCT": "CONF_PCT",
                 "NONCONF": "NON_CONF", "STRK": "STRK", "LAST5": "LAST_5"}
    fields = list(other_map.keys())
    comp, match, diffs = compare_rows(STANDINGS_2026_11_17, rows, "TEAM", fields,
                                      other_map=other_map, other_key="team_abbrev")
    return {"available": True, "comparisons": comp, "matches": match,
            "mismatches": len(diffs), "clubs": note_club_mismatches(diffs), "detail": diffs}


def mirror_week10_status() -> Dict[str, object]:
    """Has the mirror behind the results feed published the Week 10 finals?

    The console cannot settle Week 10 from the mirror if the mirror has not published it.
    Measured, not assumed: the row is read and its score fields are reported as printed.
    """
    path = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
    out = {"path": os.path.relpath(path, ROOT), "rows": [], "settled": 0, "unsettled": 0}
    if not os.path.exists(path):
        out["available"] = False
        return out
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("season") != "2026" or row.get("week") != "10":
                continue
            out["rows"].append({"game_id": row.get("game_id"),
                                "away": row.get("away_team"), "away_score": row.get("away_score"),
                                "home": row.get("home_team"), "home_score": row.get("home_score")})
    out["available"] = True
    out["settled"] = sum(1 for r in out["rows"] if (r["home_score"] or "").strip())
    out["unsettled"] = len(out["rows"]) - out["settled"]
    return out


def price_coverage_2026() -> Dict[str, object]:
    """Which 2026 markets in the price store carry both ends, by origination step.

    This is the gate on re-originating 2026: a knockout price that is only recorded now
    would be labelled with its true clock time, which is why the clock time is the point.
    """
    path = os.path.join(ROOT, "data", "console", "price_snapshots.csv")
    out: Dict[str, object] = {"available": os.path.exists(path), "rows": 0, "both": 0,
                              "by_step": {}}
    if not out["available"]:
        return out
    by_step: Dict[str, Dict[str, int]] = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("season") != "2026":
                continue
            out["rows"] += 1
            both = bool((row.get("open_line") or "").strip()) and bool(
                (row.get("close_line") or "").strip())
            if both:
                out["both"] += 1
            step = row.get("origination_step") or "?"
            b = by_step.setdefault(step, {"rows": 0, "both": 0})
            b["rows"] += 1
            b["both"] += 1 if both else 0
    out["by_step"] = by_step
    return out


def drift_state() -> Dict[str, object]:
    """What the capture gate currently sees, read from the committed status file."""
    import json
    path = os.path.join(ROOT, "data", "captures", "status.json")
    out: Dict[str, object] = {"available": os.path.exists(path), "alarms": [],
                              "datasets": {}, "generated_at": ""}
    if not out["available"]:
        return out
    with open(path, encoding="utf-8") as fh:
        st = json.load(fh)
    out["generated_at"] = st.get("generated_at", "")
    out["captures"] = st.get("captures")
    for ds, info in (st.get("freshness") or {}).items():
        out["datasets"][ds] = {"last_drift": info.get("last_drift"),
                               "last_as_read_at": info.get("last_as_read_at"),
                               "hours_since_last_read": info.get("hours_since_last_read"),
                               "captures": info.get("captures"),
                               "distinct_payloads": info.get("distinct_payloads")}
        if (info.get("last_drift") or "pass") != "pass":
            out["alarms"].append(ds)
    return out


def publishable_fields() -> Dict[str, object]:
    """Which of the 17 transcribed fields this pack publishes, and which it withholds.

    ``DIVPCT`` and ``CONFPCT`` appear on the league's page. The text extraction this session
    used rendered them inside the adjacent split-record cell, so the two percentages could not
    be read as separate cells with confidence. They are withheld rather than inferred from
    W/L/T: a division percentage is exactly the kind of number a reader would trust without
    re-deriving, and recomputing it here would publish arithmetic as if it were a read.
    Every other field was read from its own cell.
    """
    return {
        "publishable_fields": [c for c in STANDINGS_COLS
                               if c not in ("DIVPCT", "CONFPCT")],
        "withheld_fields": ["DIVPCT", "CONFPCT"],
        "withheld_reasons": {
            "DIVPCT": "the page prints it, but this read could not separate it from the "
                      "adjacent division-record cell; not inferred from W/L/T",
            "CONFPCT": "same as DIVPCT, for the conference percentage",
        },
    }


def build() -> Dict[str, object]:
    """Everything the published page needs, computed from the literals above."""
    closure = closure_checks(STANDINGS_2026_11_17)
    return {
        "publishable_fields": publishable_fields(),
        "read_utc": READ_UTC,
        "read_method": READ_METHOD,
        "sources": {"standings": STANDINGS_URL, "week10": SCHEDULE_URL, "week11": WEEK11_URL},
        "standings": STANDINGS_2026_11_17,
        "week10": WEEK10_FINALS_2026_11_17,
        "byes_week10": [{"club": c, "record": r} for c, r in BYES_WEEK10_2026_11_17],
        "games_played_implied": games_played_from_standings(STANDINGS_2026_11_17),
        "closure": closure,
        "week10_vs_standings": week10_scores_check(),
        "published_vs_league": published_vs_league(),
        "collector_vs_league": collector_vs_league(),
        "mirror_week10": mirror_week10_status(),
        "price_2026": price_coverage_2026(),
        "drift": drift_state(),
    }


if __name__ == "__main__":
    import json
    b = build()
    print(json.dumps({k: v for k, v in b.items() if k not in ("standings", "week10", "closure")},
                     indent=1)[:4000])
    print("closure:", json.dumps(b["closure"], indent=1))
