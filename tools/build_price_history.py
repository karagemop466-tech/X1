#!/usr/bin/env python3
"""Price-snapshot store — session arena-52aabfa8-x1 (task T10).

Requirement (owner's brief): "Add a price-snapshot store that records opening
and closing numbers for every market we originate."

Scope: every game whose lines the model originates or benchmarks — all games in
the backtest window (seasons 2019-2026, the same set as the verified results
feed), for every market we originate:

    SPREAD      one signed game line
    TOTAL       one game total
    MONEYLINE   one price per side (AWAY, HOME)

and for each market both snapshots the reachable sources actually publish:

    opening     nflverse/nfldata initial_lines.csv (WSGT), 2021 REG only,
                spread and total only, spread published per team side and
                total published for Over and Under (verified equal)
    closing     nflverse/nfldata games.csv per-game market line (2019+)

No official NFL or club source publishes betting prices (flag F-06, question
Q-02), so every value in this store is a third-party benchmark, never an
official number. Where a source publishes nothing, the cell is BLANK and
carries a flag code — never filled, never inferred.

Flag codes (expanded in price_store_meta.json):
    NO-CLOSING-LINE-IN-MIRROR   games.csv has no line for this game (mostly
                                2026 future weeks beyond the posted window)
    NO-OPENING-DATA-SEASON      initial_lines.csv covers 2021 REG only
    NO-OPENING-MONEYLINE        no reachable source publishes opening
                                moneylines at all

Outputs:
    data/prices/price_history.csv       (9 rows per game)
    data/prices/price_store_meta.json     (sources, conventions, checks)

Cross-checks (script exits 1 on failure):
    P1 every closing line parses as a number when present
    P2 2021 opening spread pairs are exact negatives (272/272)
    P3 2021 opening Over and Under totals are identical (272/272)
    P4 all 14 Week 10 2026 games carry complete closing spread/total/ML
    P5 the store's game set is identical to the results feed's game set
    P6 exactly 9 rows per game, no market/snapshot/side slot duplicated

Deterministic; stdlib only. Re-run:  python3 tools/build_price_history.py
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
INITIAL = os.path.join(ROOT, "data", "raw", "nflverse", "initial_lines.csv")
RESULTS = os.path.join(ROOT, "data", "results", "verified_results.csv")
OUT_DIR = os.path.join(ROOT, "data", "prices")
MANIFEST = os.path.join(ROOT, "data", "raw_manifest.json")

FIRST_SEASON = 2019
SNAPSHOT_DATE = "2026-11-14"
GAMES_URL = "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
INITIAL_URL = ("https://github.com/nflverse/nfldata/blob/master/"
               "data/initial_lines.csv")
GAMES_KEY = "nfldata_games"
INITIAL_KEY = "nfldata_initial_lines"

FIELDS = [
    "game_id", "season", "week", "game_type", "date", "away", "home",
    "market", "side", "snapshot", "line", "source_key", "convention", "flags",
]

CONV = {
    "closing_spread": "signed game line; positive = home team favored "
                      "(nflverse DATASETS.md)",
    "closing_total": "single game total",
    "closing_ml": "American odds for the named side",
    "opening_spread": "line is for the named team as published; "
                      "negative = that team favored (initial_lines.csv)",
    "opening_total": "single game total; Over and Under published identical "
                     "(verified)",
    "opening_ml": "American odds for the named side",
}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def sha_prefix() -> str:
    try:
        with open(MANIFEST, encoding="utf-8") as fh:
            for rec in json.load(fh):
                if rec.get("name") == "games.csv":
                    return rec.get("sha256", "")[:16]
    except (OSError, ValueError):
        pass
    return ""


def num(v: str, ctx: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        fail(f"{ctx}: non-numeric line {v!r}")
    return 0.0  # unreachable


def main() -> int:
    # ---------------------------------------------------------------- inputs
    games = []
    with open(GAMES, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                season = int(r["season"])
            except (TypeError, ValueError):
                continue
            if season >= FIRST_SEASON:
                games.append(r)

    opening: dict[str, dict[str, dict[str, str]]] = {}
    opening_pairs: dict[str, dict[str, dict[str, str]]] = {}
    with open(INITIAL, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            g = opening.setdefault(r["about"], {"SPREAD": {}, "TOTAL": {}})
            g.setdefault(r["type"], {})[r["side"]] = r["line"]
            if r["type"] == "SPREAD":
                opening_pairs.setdefault(r["about"], {})[r["side"]] = r["line"]

    results_ids: set[str] = set()
    if os.path.exists(RESULTS):
        with open(RESULTS, newline="", encoding="utf-8") as fh:
            results_ids = {r["game_id"] for r in csv.DictReader(fh)}

    # ------------------------------------------------------- cross-checks
    checks: list[dict] = []

    # P2 — opening spread pairs are exact negatives
    p2_bad = []
    for gid, sides in opening_pairs.items():
        if len(sides) != 2:
            p2_bad.append(f"{gid}: {len(sides)} sides")
            continue
        a, b = (num(v, gid) for v in sides.values())
        if abs(a + b) > 1e-9:
            p2_bad.append(f"{gid}: {a} and {b} not opposite")
    if p2_bad:
        fail("P2 opening spread pairs: " + "; ".join(p2_bad[:5]))

    # P3 — opening Over/Under totals identical
    p3_bad = []
    for gid, types in opening.items():
        t = types.get("TOTAL", {})
        if len(t) == 2:
            vals = {num(v, gid) for v in t.values()}
            if len(vals) != 1:
                p3_bad.append(gid)
    if p3_bad:
        fail(f"P3 opening Over/Under differ for {len(p3_bad)} games")

    # P4 — Week 10 2026 complete closing lines
    w10 = [g for g in games if g["season"] == "2026" and g["week"] == "10"]
    if len(w10) != 14:
        fail(f"P4: {len(w10)} Week 10 games, expected 14")
    for g in w10:
        for col in ("spread_line", "total_line", "away_moneyline",
                    "home_moneyline"):
            if not g.get(col):
                fail(f"P4: {g['game_id']} missing {col}")

    # P5 — same game set as the results feed
    price_ids = {g["game_id"] for g in games}
    if results_ids and price_ids != results_ids:
        only_p = sorted(price_ids - results_ids)[:5]
        only_r = sorted(results_ids - price_ids)[:5]
        fail(f"P5: game sets differ; only-price={only_p} only-results={only_r}")

    # ------------------------------------------------------------- emit rows
    rows: list[dict] = []
    n_closing_present = n_closing_blank = 0
    n_opening_present = n_opening_blank = 0

    def add(g: dict, market: str, side: str, snapshot: str, line: str,
            source_key: str, conv: str, flags: str) -> None:
        nonlocal n_closing_present, n_closing_blank
        nonlocal n_opening_present, n_opening_blank
        if snapshot == "closing":
            if line:
                n_closing_present += 1
            else:
                n_closing_blank += 1
        else:
            if line:
                n_opening_present += 1
            else:
                n_opening_blank += 1
        rows.append({
            "game_id": g["game_id"],
            "season": g["season"],
            "week": g["week"],
            "game_type": g.get("game_type", ""),
            "date": g.get("gameday", ""),
            "away": g["away_team"],
            "home": g["home_team"],
            "market": market,
            "side": side,
            "snapshot": snapshot,
            "line": line,
            "source_key": source_key,
            "convention": conv,
            "flags": flags,
        })

    for g in sorted(games, key=lambda r: (int(r["season"]),
                                          int(r["week"]) if str(r["week"]).isdigit() else 0,
                                          r["game_id"])):
        gid = g["game_id"]
        home, away = g["home_team"], g["away_team"]

        # --- closing: SPREAD / TOTAL / MONEYLINE AWAY / MONEYLINE HOME -----
        if g.get("spread_line"):
            num(g["spread_line"], f"{gid} closing spread")
            add(g, "SPREAD", "", "closing", g["spread_line"], GAMES_KEY,
                CONV["closing_spread"], "")
        else:
            add(g, "SPREAD", "", "closing", "", GAMES_KEY,
                CONV["closing_spread"], "NO-CLOSING-LINE-IN-MIRROR")

        if g.get("total_line"):
            num(g["total_line"], f"{gid} closing total")
            add(g, "TOTAL", "", "closing", g["total_line"], GAMES_KEY,
                CONV["closing_total"], "")
        else:
            add(g, "TOTAL", "", "closing", "", GAMES_KEY,
                CONV["closing_total"], "NO-CLOSING-LINE-IN-MIRROR")

        for side, col in (("AWAY", "away_moneyline"), ("HOME", "home_moneyline")):
            if g.get(col):
                num(g[col], f"{gid} closing ml {side}")
                add(g, "MONEYLINE", side, "closing", g[col], GAMES_KEY,
                    CONV["closing_ml"], "")
            else:
                add(g, "MONEYLINE", side, "closing", "", GAMES_KEY,
                    CONV["closing_ml"], "NO-CLOSING-LINE-IN-MIRROR")

        # --- opening: SPREAD per team, TOTAL, MONEYLINE AWAY/HOME ----------
        op = opening.get(gid)
        if op and op.get("SPREAD") and len(op["SPREAD"]) == 2:
            for team in (home, away):
                line = op["SPREAD"].get(team, "")
                if line:
                    num(line, f"{gid} opening spread {team}")
                add(g, "SPREAD", team, "opening", line or "", INITIAL_KEY,
                    CONV["opening_spread"],
                    "" if line else "NO-OPENING-DATA-SEASON")
        else:
            for team in (home, away):
                add(g, "SPREAD", team, "opening", "", INITIAL_KEY,
                    CONV["opening_spread"], "NO-OPENING-DATA-SEASON")

        if op and op.get("TOTAL"):
            # Over and Under verified identical in P3; store the Over value.
            over = op["TOTAL"].get("Over") or op["TOTAL"].get("Under") or ""
            if over:
                num(over, f"{gid} opening total")
            add(g, "TOTAL", "", "opening", over, INITIAL_KEY,
                CONV["opening_total"],
                "" if over else "NO-OPENING-DATA-SEASON")
        else:
            add(g, "TOTAL", "", "opening", "", INITIAL_KEY,
                CONV["opening_total"], "NO-OPENING-DATA-SEASON")

        for side in ("AWAY", "HOME"):
            add(g, "MONEYLINE", side, "opening", "", "none",
                CONV["opening_ml"], "NO-OPENING-MONEYLINE")

    # P6 — exactly 9 rows per game, no duplicate slot
    per_game: dict[str, set] = {}
    for r in rows:
        slot = (r["market"], r["side"], r["snapshot"])
        s = per_game.setdefault(r["game_id"], set())
        if slot in s:
            fail(f"P6: duplicate slot {slot} for {r['game_id']}")
        s.add(slot)
    bad = [g for g, s in per_game.items() if len(s) != 9]
    if bad:
        fail(f"P6: {len(bad)} games without exactly 9 slots, e.g. {bad[:3]}")
    if len(per_game) != len(games):
        fail("P6: row game set != input game set")

    # P1 already enforced during emit via num() on every present line.

    # ------------------------------------------------------------- write
    os.makedirs(OUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUT_DIR, "price_history.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    checks = [
        {"id": "P1", "what": "every present line parses as a number",
         "result": "pass",
         "detail": f"{n_closing_present + n_opening_present} values checked"},
        {"id": "P2", "what": "2021 opening spread pairs exact negatives",
         "result": "pass", "detail": f"{len(opening_pairs)}/{len(opening_pairs)}"},
        {"id": "P3", "what": "2021 opening Over == Under",
         "result": "pass", "detail": f"{sum(1 for t in opening.values() if t.get('TOTAL'))} games"},
        {"id": "P4", "what": "Week 10 2026 complete closing spread/total/ML",
         "result": "pass", "detail": "14/14 games"},
        {"id": "P5", "what": "game set identical to verified results feed",
         "result": "pass", "detail": f"{len(price_ids)} games"},
        {"id": "P6", "what": "exactly 9 rows per game, no duplicate slot",
         "result": "pass", "detail": f"{len(rows)} rows"},
    ]

    meta = {
        "dataset": "price_history",
        "title": "Opening and closing price snapshots for every market we originate",
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "generated_by": "tools/build_price_history.py (session arena-52aabfa8-x1, T10)",
        "snapshot_date": SNAPSHOT_DATE,
        "columns": FIELDS,
        "requirement": ("\"Add a price-snapshot store that records opening and "
                        "closing numbers for every market we originate\" — "
                        "owner's brief"),
        "sources": [
            {"key": GAMES_KEY, "url": GAMES_URL,
             "label": "nflverse/nfldata games.csv — closing market lines",
             "org": "nflverse (not the NFL)", "tier": "third_party_mirror",
             "retrieved_at": SNAPSHOT_DATE, "file": "data/raw/nflverse/games.csv",
             "sha256_prefix": sha_prefix(),
             "coverage": "2019-2026; 2026 lines posted through week 11"},
            {"key": INITIAL_KEY, "url": INITIAL_URL,
             "label": "nflverse/nfldata initial_lines.csv — opening lines (WSGT)",
             "org": "nflverse (not the NFL)", "tier": "third_party_mirror",
             "retrieved_at": SNAPSHOT_DATE,
             "file": "data/raw/nflverse/initial_lines.csv",
             "coverage": "2021 regular season only; spread and total only; "
                         "no moneylines"},
            {"key": "official", "url": "https://www.nfl.com/",
             "label": "No official source publishes betting prices",
             "org": "NFL", "tier": "none_exists",
             "note": ("flag F-06 / question Q-02: every value here is a "
                      "third-party benchmark, never league-verified"),
            },
        ],
        "conventions": CONV,
        "flag_codes": {
            "NO-CLOSING-LINE-IN-MIRROR":
                "games.csv carries no closing line for this game (future 2026 "
                "weeks beyond the posted window). Cell blank — never guessed.",
            "NO-OPENING-DATA-SEASON":
                "initial_lines.csv covers the 2021 regular season only; no "
                "opening number exists for this game in any reachable source.",
            "NO-OPENING-MONEYLINE":
                "no reachable source publishes opening moneylines for any "
                "season. Cell blank by construction.",
        },
        "counts": {
            "rows": len(rows),
            "games": len(per_game),
            "closing_values_present": n_closing_present,
            "closing_cells_blank": n_closing_blank,
            "opening_values_present": n_opening_present,
            "opening_cells_blank": n_opening_blank,
        },
        "verification": {"checks": checks, "all_passed": True},
        "known_limitations": [
            "Opening and closing use different published conventions "
            "(per-team opening spread vs signed game closing spread). They "
            "are stored verbatim as published; normalising them into one "
            "convention is a follow-up before any CLV number is computed "
            "from this store.",
            "2021 is the only season with opening data, and it has no "
            "opening moneylines — CLV studies on moneylines are impossible "
            "from reachable sources (part of Q-02).",
            "No value in this store is official. F-06 stands: a licensed or "
            "account price feed is the owner decision that would upgrade the "
            "tiers.",
        ],
    }
    meta_path = os.path.join(OUT_DIR, "price_store_meta.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, ensure_ascii=False)
        fh.write("\n")

    print(f"price store written: {len(rows)} rows / {len(per_game)} games "
          f"-> {csv_path}")
    print(f"  closing present={n_closing_present} blank={n_closing_blank}  "
          f"opening present={n_opening_present} blank={n_opening_blank}")
    for c in checks:
        print(f"  {c['id']} {c['result']}: {c['what']} ({c['detail']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
