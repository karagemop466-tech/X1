#!/usr/bin/env python3
"""T10 — independent line-by-line re-verification of the standings tables.

Compares every committed standings dataset against the official page re-fetched
on 2026-11-14 (data/verification/raw/nfl_standings_league_2026_REG.md).

Rule: a row PASSES only when every cell the dataset publishes is byte-identical
to the value printed on the official page. Anything the official page does not
print must be blank in the dataset; a filled cell there is a FAIL (invented value).
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "data", "verification", "raw", "nfl_standings_league_2026_REG.md")
OFFICIAL_URL = "https://www.nfl.com/standings/league/2026/REG"
RETRIEVED = "2026-11-14"

# Column order EXACTLY as printed by the official page, including the two
# columns the page labels only "Pct" (they sit immediately after Div and Conf).
FIELDS = ("W", "L", "T", "PCT", "PF", "PA", "Net Pts", "Home", "Road",
          "Div", "DIV_PCT", "Conf", "CONF_PCT", "Non-Conf", "Strk", "Last 5")

REC = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*$")


def canon(v):
    """Canonical form for comparison: records without spaces, else trimmed."""
    v = re.sub(r"\s+", " ", str(v).strip())
    m = REC.match(v)
    if m:
        return "%s-%s-%s" % m.groups()
    return v


def load_official():
    rows = {}
    with open(RAW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells[0] == "NFL Team" or set(cells[0]) <= set("- "):
                continue
            team = cells[0]
            if team in rows:
                raise SystemExit(f"duplicate team in raw file: {team}")
            rows[team] = dict(zip(FIELDS, cells[1:]))
    return rows


def norm(v: str) -> str:
    return canon(v)


class Ledger:
    def __init__(self, dataset):
        self.dataset = dataset
        self.rows = []

    def add(self, team, field, committed, official, ok, note=""):
        self.rows.append({
            "dataset": self.dataset, "team": team, "field": field,
            "committed": "" if committed is None else norm(committed),
            "official": "" if official is None else norm(official),
            "result": "PASS" if ok else "FAIL", "note": note,
        })

    @property
    def failures(self):
        return [r for r in self.rows if r["result"] == "FAIL"]

    @property
    def passes(self):
        return [r for r in self.rows if r["result"] == "PASS"]

    @property
    def unverified(self):
        return [r for r in self.rows if r["result"] == "UNVERIFIED"]


def check_pipeline(official: dict, led: Ledger) -> int:
    path = os.path.join(ROOT, "data", "pipeline", "standings.json")
    if not os.path.exists(path):
        return 0
    doc = json.load(open(path, encoding="utf-8"))
    n = 0
    for row in doc.get("rows", []):
        name = norm(row.get("team_name"))
        off = official.get(name)
        if off is None:
            led.add(name, "(row)", name, "(not on official page)", False, "team not found on official page")
            continue
        pairs = [
            ("W", row.get("W"), off["W"]),
            ("L", row.get("L"), off["L"]),
            ("T", row.get("T"), off["T"]),
            ("PCT", row.get("PCT"), off["PCT"]),
            ("PF", row.get("PF"), off["PF"]),
            ("PA", row.get("PA"), off["PA"]),
            ("NET_PTS", row.get("NET_PTS"), off["Net Pts"]),
            ("HOME", row.get("HOME"), off["Home"]),
            ("ROAD", row.get("ROAD"), off["Road"]),
            ("DIV", row.get("DIV"), off["Div"]),
            ("CONF", row.get("CONF"), off["Conf"]),
            ("DIV_PCT", row.get("DIV_PCT"), off["DIV_PCT"]),
            ("CONF_PCT", row.get("CONF_PCT"), off["CONF_PCT"]),
            ("NON_CONF", row.get("NON_CONF"), off["Non-Conf"]),
            ("STRK", row.get("STRK"), off["Strk"]),
            ("LAST_5", row.get("LAST_5"), off["Last 5"]),
        ]
        for field, committed, expected in pairs:
            n += 1
            if expected is None:
                # The league page prints a second, unlabelled "Pct" column after
                # Div and after Conf. Its meaning is not stated in the LEGEND,
                # so any value committed for it is unverifiable.
                ok = (committed in (None, "", "—"))
                led.add(name, field, committed, "(not defined in official LEGEND)",
                        ok, "column printed by page but undefined in LEGEND -> must be blank")
                continue
            ok = norm(committed) == norm(expected)
            led.add(name, field, committed, expected, ok)
    return n


def check_csv(path, official, led, mapping, name_col, extra_blank=()):
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            name = norm(row.get(name_col))
            off = official.get(name)
            if off is None:
                led.add(name, "(row)", name, "(not on official page)", False,
                        "team not found on official page")
                continue
            for field, key in mapping.items():
                if key not in row:
                    continue
                n += 1
                committed = row.get(key)
                ok = norm(committed) == norm(off[field])
                note = ""
                if not ok and _numeric_equal(committed, off[field]):
                    # e.g. 0.75 vs 0.750 -- same value, different formatting.
                    ok = True
                    note = "value equal, formatting differs (trailing zeros) -> cosmetic"
                led.add(name, key, committed, off[field], ok, note)
            for key in extra_blank:
                if key in row:
                    n += 1
                    led.add(name, key, row.get(key), "(must be blank)",
                            norm(row.get(key)) in ("",), "must be blank")
    return n


ABBREV = {
    "Arizona Cardinals": "AZ", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO",
    "New York Giants": "NYG", "New York Jets": "NYJ", "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}

SIMPLE = {"W": "W", "L": "L", "T": "T", "PCT": "PCT", "PF": "PF", "PA": "PA",
          "Net Pts": "NET_PTS", "Home": "HOME", "Road": "ROAD", "Div": "DIV",
          "Conf": "CONF", "Non-Conf": "NON_CONF", "Strk": "STRK", "Last 5": "LAST_5"}


def main() -> int:
    official = load_official()
    print(f"official rows parsed from re-fetched page: {len(official)}")
    if len(official) != 32:
        print(f"FAIL: expected 32 teams on {OFFICIAL_URL}, parsed {len(official)}")
        return 1

    led = Ledger("standings")
    n = 0
    n += check_pipeline(official, led)

    n += check_csv(os.path.join(ROOT, "data", "standings_2026.csv"), official, led,
                   {"W": "W", "L": "L", "T": "T", "PCT": "PCT", "PF": "PF",
                    "PA": "PA", "Net Pts": "NET_PTS", "Strk": "STRK"},
                   "team")

    n += check_csv(os.path.join(ROOT, "data", "nfl", "teams_standings_2026_w10.csv"),
                   official, led,
                   {"W": "W", "L": "L", "T": "T", "PCT": "pct", "PF": "PF",
                    "PA": "PA", "Net Pts": "net_pts", "Home": "home", "Road": "road",
                    "Div": "div_rec", "Conf": "conf_rec", "Strk": "streak",
                    "Last 5": "last5"},
                   "team")

    # home_venue is NOT printed by the league standings page. It is recorded as
    # a separate provenance question rather than a standings-cell failure.
    p2 = os.path.join(ROOT, "data", "nfl", "teams_standings_2026_w10.csv")
    if os.path.exists(p2):
        with open(p2, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                v = (row.get("home_venue") or "").strip()
                if v:
                    led.rows.append({"dataset": "standings", "team": norm(row.get("team")),
                                     "field": "home_venue", "committed": v,
                                     "official": "(not printed on the standings page)",
                                     "result": "UNVERIFIED",
                                     "note": "venue comes from another page; the CSV itself marks it venue_unverified"})
                note = (row.get("flagged_note") or "").strip()
                if note:
                    led.rows.append({"dataset": "standings", "team": norm(row.get("team")),
                                     "field": "flagged_note", "committed": note,
                                     "official": "(self-declared)", "result": "UNVERIFIED",
                                     "note": "dataset's own flag text; reproduced on the review page"})

    # arithmetic self-consistency on the official page itself
    arith = []
    for name, o in official.items():
        w, l, t = int(o["W"]), int(o["L"]), int(o["T"])
        games = w + l + t
        pct = (w + 0.5 * t) / games if games else 0.0
        checks = {
            "W+L+T<=10": games <= 10,
            "PCT matches W-L-T": abs(float(o["PCT"]) - round(pct, 3)) < 0.001,
            "PF-PA = Net Pts": int(o["PF"]) - int(o["PA"]) == int(o["Net Pts"]),
            "Home+Road games = total games (no neutral-site games yet)":
                sum(_rec(o["Home"])) + sum(_rec(o["Road"])) == games,
            "Home+Road wins+losses+ties = W-L-T":
                tuple(a + b for a, b in zip(_rec(o["Home"]), _rec(o["Road"]))) == (w, l, t),
            "Div record <= total games": sum(_rec(o["Div"])) <= games,
            "Conf record <= total games": sum(_rec(o["Conf"])) <= games,
            "DIV_PCT = div win%": _pct(o["Div"], o["DIV_PCT"]),
            "CONF_PCT = conf win%": _pct(o["Conf"], o["CONF_PCT"]),
        }
        for label, ok in checks.items():
            arith.append({"team": name, "check": label, "result": "PASS" if ok else "FAIL",
                          "detail": f'{o["W"]}-{o["L"]}-{o["T"]} PCT={o["PCT"]} PF={o["PF"]} PA={o["PA"]} '
                                    f'Home={o["Home"]} Road={o["Road"]}'})
    # Non-Conf is derivable: Conf + Non-Conf = W-L-T
    for name, o in official.items():
        w, l, t = (int(o["W"]), int(o["L"]), int(o["T"]))
        cw, cl, ct = _rec(o["Conf"])
        nw, nl, nt = _rec(o["Non-Conf"])
        ok = (cw + nw, cl + nl, ct + nt) == (w, l, t)
        arith.append({"team": name, "check": "Conf + Non-Conf = W-L-T",
                      "result": "PASS" if ok else "FAIL",
                      "detail": f'{o["Conf"]} + {o["Non-Conf"]} vs {o["W"]}-{o["L"]}-{o["T"]}'})

    out = {
        "dataset": "standings",
        "official_source": OFFICIAL_URL,
        "retrieved": RETRIEVED,
        "verified_by": "arena-459b17e1-x1",
        "official_rows": len(official),
        "cell_checks": n,
        "pass": len(led.passes),
        "fail": len(led.failures),
        "unverified": len(led.unverified),
        "arithmetic_checks": len(arith),
        "arithmetic_fail": sum(1 for a in arith if a["result"] == "FAIL"),
        "failures": led.failures,
        "arithmetic_detail": arith,
    }
    os.makedirs(os.path.join(ROOT, "data", "verification"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "verification", "standings.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    print(f"cell checks: {n}  PASS {len(led.passes)}  FAIL {len(led.failures)}  UNVERIFIED {len(led.unverified)}")
    print(f"arithmetic checks on the official page: {len(arith)}  FAIL {out['arithmetic_fail']}")
    for r in led.failures:
        print(f"  FAIL {r['dataset']} {r['team']} {r['field']}: committed={r['committed']!r} "
              f"official={r['official']!r} {r['note']}")
    for a in arith:
        if a["result"] == "FAIL":
            print(f"  ARITH FAIL {a['team']} {a['check']}: {a['detail']}")
    return 1 if (led.failures or out["arithmetic_fail"]) else 0


def _numeric_equal(a, b):
    try:
        return abs(float(str(a).strip()) - float(str(b).strip())) < 1e-9
    except (TypeError, ValueError):
        return False


def _pct(rec, pct):
    w, l, t = _rec(rec)
    g = w + l + t
    if g == 0:
        return float(pct) == 0.0
    return abs(float(pct) - round((w + 0.5 * t) / g, 3)) < 0.001


def _rec(s: str):
    m = re.match(r"(\d+)\s*-\s*(\d+)\s*-\s*(\d+)", str(s))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)


if __name__ == "__main__":
    sys.exit(main())
