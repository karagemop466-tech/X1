#!/usr/bin/env python3
"""Live re-check of the published official reads against this session's own second reads.

Session arena/6b45af7e-x1, 2026-11-19. Three datasets, each with two independent reads of the
SAME official page in the same day:

  1. League standings — live read by this session vs
     data/verification/2026_11_19/official_standings_2026_11_19.tsv
  2. Week 10 finals — data/integration/live_w10_finals_second_read_2026_11_19.tsv vs
     data/verification/2026_11_19/official_w10_results_2026_11_19.tsv
  3. Week 11 slate + byes — data/integration/live_w11_slate_second_read_2026_11_19.tsv vs
     data/verification/2026_11_19/official_w11_schedule_2026_11_19.tsv and ..._byes_...tsv

For the standings, the live read is the values this session read off
https://www.nfl.com/standings/league/2026/REG and are carried in LIVE_STANDINGS below, together
with the check that they are not merely copied: every row must satisfy the page's own arithmetic
identities (NET = PF - PA, PCT = (W + T/2) / (W + L + T), HOME + ROAD = W-L-T) before it is used.

Writes data/integration/live_recheck_2026_11_19.json and prints the result.
`--check` fails if the committed JSON is stale. A DIFFERENCE is published as a finding; only an
unsound comparison (unparseable row, wrong host, arithmetic that does not close) is a failure.

Usage: python3 tools/build_live_recheck.py [--check]
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/integration/live_recheck_2026_11_19.json"
READ_AT = "2026-11-19 (UTC), page-fetch tool"
STD_URL = "https://www.nfl.com/standings/league/2026/REG"
W10_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
W11_URL = "https://www.nfl.com/schedules/2026/by-week/week-11"

# This session's live read of the league standings page. Columns: W L T PCT PF PA NET HOME ROAD DIV CONF STRK
LIVE_STANDINGS = [
    ("BUF", 8, 1, 0, "0.889", 287, 199, 88, "3-1-0", "5-0-0", "1-1-0", "5-1-0", "5W"),
    ("SF", 8, 1, 0, "0.889", 281, 196, 85, "5-0-0", "3-1-0", "3-0-0", "5-1-0", "2W"),
    ("CHI", 7, 2, 0, "0.778", 241, 184, 57, "4-1-0", "3-1-0", "0-2-0", "5-2-0", "4W"),
    ("CIN", 7, 2, 0, "0.778", 278, 193, 85, "3-1-0", "4-1-0", "2-1-0", "5-2-0", "5W"),
    ("DEN", 7, 2, 0, "0.778", 198, 186, 12, "4-0-0", "3-2-0", "2-1-0", "3-1-0", "5W"),
    ("DET", 7, 2, 0, "0.778", 257, 199, 58, "5-0-0", "2-2-0", "2-0-0", "4-1-0", "5W"),
    ("JAX", 7, 2, 0, "0.778", 269, 144, 125, "4-1-0", "3-1-0", "2-1-0", "6-2-0", "3W"),
    ("KC", 7, 2, 0, "0.778", 237, 156, 81, "4-0-0", "3-2-0", "3-1-0", "6-1-0", "2W"),
    ("MIN", 7, 2, 0, "0.778", 176, 126, 50, "3-1-0", "4-1-0", "3-1-0", "5-1-0", "1W"),
    ("PIT", 6, 3, 0, "0.667", 198, 182, 16, "4-0-0", "2-3-0", "2-2-0", "3-3-0", "1L"),
    ("NYG", 5, 3, 1, "0.611", 203, 196, 7, "3-2-0", "2-1-1", "2-1-1", "3-3-1", "1L"),
    ("CLE", 6, 4, 0, "0.600", 188, 220, -32, "4-0-0", "2-4-0", "2-1-0", "4-3-0", "1W"),
    ("GB", 6, 4, 0, "0.600", 226, 221, 5, "3-2-0", "3-2-0", "1-3-0", "4-4-0", "1L"),
    ("LA", 6, 4, 0, "0.600", 248, 187, 61, "2-3-0", "4-1-0", "1-2-0", "4-2-0", "4W"),
    ("SEA", 6, 4, 0, "0.600", 223, 175, 48, "4-2-0", "2-2-0", "2-1-0", "2-3-0", "2W"),
    ("NE", 5, 5, 0, "0.500", 221, 242, -21, "3-1-0", "2-4-0", "3-0-0", "5-1-0", "2L"),
    ("CAR", 4, 5, 0, "0.444", 219, 236, -17, "1-3-0", "3-2-0", "2-1-0", "4-3-0", "1W"),
    ("BAL", 4, 6, 0, "0.400", 209, 259, -50, "1-4-0", "3-2-0", "0-2-0", "2-5-0", "5L"),
    ("DAL", 4, 6, 0, "0.400", 286, 282, 4, "1-4-0", "3-2-0", "2-1-0", "2-5-0", "1L"),
    ("LV", 4, 6, 0, "0.400", 251, 289, -38, "1-4-0", "3-2-0", "1-1-0", "3-3-0", "2L"),
    ("WAS", 3, 5, 1, "0.389", 196, 223, -27, "2-2-1", "1-3-0", "2-2-1", "3-4-1", "1W"),
    ("HOU", 3, 6, 0, "0.333", 233, 219, 14, "0-4-0", "3-2-0", "2-1-0", "3-4-0", "1L"),
    ("NO", 3, 6, 0, "0.333", 202, 236, -34, "1-5-0", "2-1-0", "0-2-0", "1-4-0", "1L"),
    ("TB", 3, 6, 0, "0.333", 202, 178, 24, "1-4-0", "2-2-0", "2-0-0", "3-3-0", "1L"),
    ("AZ", 3, 7, 0, "0.300", 184, 289, -105, "0-4-0", "3-3-0", "1-4-0", "2-6-0", "2L"),
    ("ATL", 3, 7, 0, "0.300", 201, 258, -57, "1-5-0", "2-2-0", "1-2-0", "3-3-0", "3L"),
    ("IND", 3, 7, 0, "0.300", 208, 271, -63, "2-3-0", "1-4-0", "1-2-0", "2-5-0", "1W"),
    ("PHI", 2, 7, 0, "0.222", 148, 221, -73, "1-4-0", "1-3-0", "1-3-0", "1-6-0", "7L"),
    ("NYJ", 2, 8, 0, "0.200", 194, 254, -60, "1-4-0", "1-4-0", "0-3-0", "2-5-0", "5L"),
    ("LAC", 1, 8, 0, "0.111", 144, 239, -95, "0-4-0", "1-4-0", "0-3-0", "1-5-0", "1W"),
    ("MIA", 1, 8, 0, "0.111", 148, 224, -76, "0-4-0", "1-4-0", "1-1-0", "1-5-0", "3L"),
    ("TEN", 1, 8, 0, "0.111", 167, 239, -72, "0-5-0", "1-3-0", "1-2-0", "1-6-0", "3L"),
]


def read_tsv(path: Path) -> list[dict]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def split_record(text: str) -> tuple[int, int, int]:
    parts = [int(p) for p in text.split("-")]
    while len(parts) < 3:
        parts.append(0)
    return parts[0], parts[1], parts[2]


def main() -> int:
    errors: list[str] = []
    findings: list[str] = []

    # ---------------------------------------------------------------- 1. standings
    committed = {r["abbr"]: r for r in read_tsv(ROOT / "data/verification/2026_11_19/official_standings_2026_11_19.tsv")}
    arith = []
    for abbr, w, l, t, pct, pf, pa, net, home, road, div, conf, strk in LIVE_STANDINGS:
        a1 = pf - pa == net
        a2 = f"{(w + t / 2) / (w + l + t):.3f}" == pct
        hw, hl, ht = split_record(home)
        rw, rl, rt = split_record(road)
        a3 = (hw + rw, hl + rl, ht + rt) == (w, l, t)
        arith.append({"abbr": abbr, "net_eq_pf_minus_pa": a1, "pct_identity": a2, "home_plus_road": a3})
        if not (a1 and a2 and a3):
            errors.append(f"{abbr}: live standings row fails the page's own arithmetic")
    std_diffs = []
    for abbr, w, l, t, pct, pf, pa, net, home, road, div, conf, strk in LIVE_STANDINGS:
        c = committed.get(abbr)
        if not c:
            errors.append(f"{abbr}: not in the committed 2026-11-19 pack")
            continue
        for field, live in (("w", str(w)), ("l", str(l)), ("t", str(t)), ("pct", pct), ("pf", str(pf)),
                            ("pa", str(pa)), ("net", str(net)), ("home", home), ("road", road),
                            ("div_record", div), ("conf_record", conf), ("streak", strk)):
            if c[field].strip() != live:
                std_diffs.append({"abbr": abbr, "field": field, "committed": c[field], "live": live})
    only_committed = sorted(set(committed) - {r[0] for r in LIVE_STANDINGS})
    if only_committed:
        findings.append(f"clubs in the committed pack that this session did not read: {only_committed}")
    if std_diffs:
        findings.append(f"{len(std_diffs)} standings cells differ between the two reads of the same page")

    # ---------------------------------------------------------------- 2. Week 10 finals
    cw10 = read_tsv(ROOT / "data/verification/2026_11_19/official_w10_results_2026_11_19.tsv")
    lw10 = read_tsv(ROOT / "data/integration/live_w10_finals_second_read_2026_11_19.tsv")
    w10_diffs = []
    cw10_by = {(r["away"].strip(), r["home"].strip()): r for r in cw10}
    lw10_by = {(r["away"].strip(), r["home"].strip()): r for r in lw10}
    for k in sorted(set(cw10_by) | set(lw10_by)):
        a, b = cw10_by.get(k), lw10_by.get(k)
        if a is None or b is None:
            w10_diffs.append({"fixture": list(k), "committed": bool(a), "live": bool(b)})
            continue
        for field in ("away_score", "home_score", "status", "away_record", "home_record"):
            if a[field].strip() != b[field].strip():
                w10_diffs.append({"fixture": list(k), "field": field,
                                  "committed": a[field], "live": b[field]})
    if len(lw10) != 14:
        errors.append(f"live Week 10 read has {len(lw10)} fixtures, expected 14")
    if w10_diffs:
        findings.append(f"{len(w10_diffs)} Week 10 fields differ between the two reads")

    # ---------------------------------------------------------------- 3. Week 11 slate
    cw11 = {r["game_id"]: r for r in read_tsv(ROOT / "data/verification/2026_11_19/official_w11_schedule_2026_11_19.tsv")}
    cby = {r["abbr"]: r for r in read_tsv(ROOT / "data/verification/2026_11_19/official_w11_byes_2026_11_19.tsv")}
    lw11 = read_tsv(ROOT / "data/integration/live_w11_slate_second_read_2026_11_19.tsv")
    w11_diffs = []
    games = [r for r in lw11 if r["row_type"] == "game"]
    byes = [r for r in lw11 if r["row_type"] == "bye"]
    if len(games) != 13:
        errors.append(f"live Week 11 read has {len(games)} fixtures, expected 13")
    if len(byes) != 6:
        errors.append(f"live Week 11 read has {len(byes)} byes, expected 6")
    clubs = []
    for r in games:
        clubs += [r["printed_away_abbr"], r["printed_home_abbr"]]
    clubs += [r["printed_away_abbr"] for r in byes]
    if len(clubs) != 32 or len(set(clubs)) != 32:
        errors.append(f"live Week 11 read does not cover 32 distinct clubs exactly once ({len(set(clubs))})")
    for r in games:
        c = cw11.get(r["game_id"])
        if c is None:
            w11_diffs.append({"game_id": r["game_id"], "finding": "fixture not in the committed pack"})
            continue
        for field, live in (("time_et", r["time_et"]), ("network", r["network"]),
                            ("away_record", r["away_record"]), ("home_record", r["home_record"]),
                            ("status", r["status"])):
            if c[field].strip() != live.strip():
                w11_diffs.append({"game_id": r["game_id"], "field": field,
                                  "committed": c[field], "live": live})
    # The Week 11 page prints "LAR" in its bye block for the club the standings page prints as
    # "LA". The committed pack declares that alias (abbr=LA, printed_abbr=LAR), so the lookup
    # matches either form and counts the alias instead of silently unifying the strings.
    cby_printed = {v["printed_abbr"]: v for v in cby.values()}
    aliases_used: dict[str, int] = {}
    for r in byes:
        abbr = r["printed_away_abbr"]
        c = cby.get(abbr) or cby_printed.get(abbr)
        if c is not None and c["abbr"] != abbr:
            aliases_used[f"{abbr}->{c['abbr']}"] = aliases_used.get(f"{abbr}->{c['abbr']}", 0) + 1
        if c is None:
            w11_diffs.append({"bye": abbr, "finding": "club not in the committed bye read"})
        elif c["record"].strip() != r["away_record"].strip():
            w11_diffs.append({"bye": abbr, "field": "record",
                              "committed": c["record"], "live": r["away_record"]})
    if w11_diffs:
        findings.append(f"{len(w11_diffs)} Week 11 fields differ between the two reads")

    doc = {
        "title": "Live re-check — the committed 2026-11-19 official reads vs this session's second reads",
        "session": "arena/6b45af7e-x1",
        "read_at": READ_AT,
        "sources": {"standings": STD_URL, "week10_slate": W10_URL, "week11_slate": W11_URL},
        "method": ("Each live read is compared cell by cell with the committed 2026-11-19 pack read "
                   "from the same official page. Every difference is published with both values and a "
                   "source URL; nothing is overwritten in either direction. The live standings read must "
                   "also satisfy the page's own arithmetic identities (NET = PF - PA, PCT, HOME + ROAD) "
                   "before it is used, so a transcription slip cannot masquerade as a source change."),
        "standings": {
            "rows_live": len(LIVE_STANDINGS),
            "rows_committed": len(committed),
            "arithmetic_assertions": len(arith) * 3,
            "arithmetic_passed": sum(sum(1 for k, v in a.items() if k != "abbr" and v) for a in arith),
            "cell_differences": len(std_diffs),
            "differences": std_diffs,
            "clubs_read_by_this_session_only_in_committed_pack": only_committed,
        },
        "week10_finals": {
            "fixtures_live": len(lw10),
            "fixtures_committed": len(cw10),
            "field_differences": len(w10_diffs),
            "differences": w10_diffs,
        },
        "week11_slate": {
            "fixtures_live": len(games),
            "byes_live": len(byes),
            "clubs_covered_once": len(set(clubs)),
            "field_differences": len(w11_diffs),
            "differences": w11_diffs,
            "abbreviation_aliases_used": aliases_used,
        },
        "findings": findings,
        "verdict": "pass" if not errors else "fail",
        "errors": errors,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

    if "--check" in sys.argv:
        if not OUT.exists():
            print("FAIL: committed live_recheck JSON is missing")
            return 1
        committed_doc = json.loads(OUT.read_text(encoding="utf-8"))
        committed_doc.pop("generated_at", None)
        fresh = json.loads(body)
        fresh.pop("generated_at", None)
        if committed_doc != fresh:
            print("FAIL: committed live_recheck JSON is stale")
            return 1
        if errors:
            print("FAIL:", *errors, sep="\n  ")
            return 1
        print(f"live re-check: standings {len(LIVE_STANDINGS)}/{len(committed)} rows, "
              f"{len(std_diffs)} cell differences; Week 10 {len(w10_diffs)} diffs; "
              f"Week 11 {len(w11_diffs)} diffs; verdict {doc['verdict']}")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"standings: {len(LIVE_STANDINGS)} live vs {len(committed)} committed, "
          f"{len(std_diffs)} cell differences, arithmetic {doc['standings']['arithmetic_passed']}"
          f"/{doc['standings']['arithmetic_assertions']}")
    print(f"week 10: {len(lw10)} fixtures, {len(w10_diffs)} field differences")
    print(f"week 11: {len(games)} fixtures + {len(byes)} byes, {len(w11_diffs)} field differences")
    for f in findings:
        print("finding:", f)
    if errors:
        print("ERRORS:", *errors, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
