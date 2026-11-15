#!/usr/bin/env python3
"""Decision-readiness register (round 4, session arena-fb9e0427-x1).

One row per requirement: the 53 rows of data/audit/requirements_assessed.json plus the
brief items that register does not carry (data/audit/readiness_gates.json, "extra").

For every row this builder publishes:
  * the state the register recorded (unchanged, shown for transparency),
  * the state this round reached after checking the data files,
  * the gate that blocks the row,
  * the value measured now, computed from a named file in this repository,
  * the number that would clear the row, and where that number comes from.

Nothing here reads the network. Every measured value is recomputed from the files on
each run, and `--check` fails if the committed data/audit/readiness.json is stale.

Usage:
  python3 tools/build_state_audit.py          # write data/audit/readiness.json
  python3 tools/build_state_audit.py --check  # exit 1 if the committed file is stale
"""

from __future__ import annotations

import csv
import glob
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG_PATH = "data/audit/requirements_assessed.json"
GATES_PATH = "data/audit/readiness_gates.json"
OUT_PATH = "data/audit/readiness.json"
ROUND_DATE = "2026-11-15"
REPO_BLOB = "https://github.com/karagemop466-tech/X1/blob/main/"

STATES = ("met", "partly met", "in progress", "open")


def p(rel: str) -> str:
    return os.path.join(ROOT, rel)


def load_json(rel: str) -> Any:
    with open(p(rel), encoding="utf-8") as fh:
        return json.load(fh)


def load_csv(rel: str) -> List[Dict[str, str]]:
    with open(p(rel), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def repo_files() -> List[str]:
    """Basenames of every file in the repository, excluding git metadata."""
    out: List[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "_site")]
        out.extend(filenames)
    return out


def count_named(files: List[str], pattern: str) -> int:
    rx = re.compile(pattern, re.I)
    return sum(1 for f in files if rx.search(f))


def fmt(n: Any) -> str:
    if isinstance(n, bool) or n is None:
        return str(n)
    if isinstance(n, int):
        return f"{n:,}"
    if isinstance(n, float):
        return f"{n:,.3f}".rstrip("0").rstrip(".")
    return str(n)


# ---------------------------------------------------------------- measurements
def measure() -> Dict[str, Any]:
    m: Dict[str, Any] = {}
    files = repo_files()

    # Price store (data/prices/price_history.csv)
    ph = load_csv("data/prices/price_history.csv")
    games = {r["game_id"] for r in ph}
    m["games"] = len(games)
    m["price_rows"] = len(ph)
    by_game: Dict[str, Dict[tuple, Dict[str, str]]] = {}
    for r in ph:
        by_game.setdefault(r["game_id"], {})[(r["market"], r["snapshot"])] = r
    for mk, key in (("SPREAD", "price_oc_spread"), ("TOTAL", "price_oc_total"), ("MONEYLINE", "price_oc_ml")):
        n = 0
        for d in by_game.values():
            o, c = d.get((mk, "opening")), d.get((mk, "closing"))
            if o and c and o["line"] and c["line"]:
                n += 1
        m[key] = n
    # No league or club source publishes betting prices, so no source key is recognised as official.
    official_price_keys: set = set()
    m["price_official"] = sum(1 for r in ph if r["source_key"] in official_price_keys)
    m["price_sources"] = sorted({r["source_key"] for r in ph})

    # Results feed (data/results/verified_results.csv)
    rs = load_csv("data/results/verified_results.csv")
    m["res_rows"] = len(rs)
    m["res_official"] = sum(1 for r in rs if r["official_verified"] == "yes")
    m["res_2026_rows"] = sum(1 for r in rs if r["season"] == "2026")
    m["res_2026_final"] = sum(1 for r in rs if r["season"] == "2026" and r["status"] == "final")
    m["res_2026_sched"] = sum(1 for r in rs if r["season"] == "2026" and r["status"] == "scheduled")

    # Injury report (data/injuries/injuries_2026_week10.csv)
    inj = load_csv("data/injuries/injuries_2026_week10.csv")
    m["inj_rows"] = len(inj)
    m["inj_dates"] = len({r["snapshot_date"] for r in inj})
    years = set()
    for dirpath, _dn, fns in os.walk(p("data")):
        for f in fns:
            if re.search(r"injur", f, re.I):
                for y in re.findall(r"(20\d{2})", f):
                    years.add(int(y))
    m["inj_seasons"] = len(years)

    # Depth charts and the club sweep (data/pipeline/*.json)
    dc = load_json("data/pipeline/depth_charts.json")["rows"]
    m["depth_clubs"] = len({r["team_abbrev"] for r in dc})
    m["standings_rows"] = len(load_json("data/pipeline/standings.json")["rows"])

    # Round-4 spot check of four clubs against the live nfl.com page (tools/spotcheck_injuries_r4.py)
    sc = load_csv("data/audit/round4_spotcheck_injuries.csv")
    m["spot_players"] = len(sc)
    m["spot_clubs"] = len({r["team"] for r in sc})
    m["spot_mismatch"] = sum(1 for r in sc if r["match"] != "yes")

    # Originated lines, Week 10 (data/lines/originated_lines_2026_week10.csv)
    ol = load_csv("data/lines/originated_lines_2026_week10.csv")
    m["orig_rows"] = len(ol)
    m["orig_market"] = sum(1 for r in ol if r["market_spread_away"])
    m["orig_official"] = 0  # the file carries no official market source; see price_official

    # Model accuracy (data/lab/lines/model_report.json)
    acc = load_json("data/lab/lines/model_report.json")["accuracy"]
    m["side_mae_model"] = acc["side_mae_model"]
    m["side_mae_market"] = acc["side_mae_market"]
    m["side_mae_gap"] = round(acc["side_mae_model"] - acc["side_mae_market"], 3)
    m["n_side"] = acc["n_side"]

    # Leaderboard (data/site/payload.json)
    payload = load_json("data/site/payload.json")
    lb = payload["leaderboard"]
    m["lb_rows"] = len(lb)
    passed = [s for s in lb if s.get("all_passed")]
    m["lb_pass"] = len(passed)
    m["lb_pass_bets"] = passed[0]["bets"] if passed else 0
    m["lb_random_control"] = sum(
        1 for s in lb if any(("random" in k.lower() or "control" in k.lower()) for k in s.keys())
    )
    m["lb_fav_roi"] = payload["baselines"]["always_favourite"]

    # Gate registers
    gates = load_json("data/gates.json")["gates"]
    g1 = next(g for g in gates if g["id"] == "G1")
    m["g1_gates"] = g1["thresholds"]["singles_bets"]
    g7 = next(g for g in gates if g["id"] == "G7")
    m["g7_families"] = len(g7["applies_to"])
    readme = open(p("README.md"), encoding="utf-8").read()
    mt = re.search(r"\| G1 \| Sample sufficiency \| >= (\d+)", readme)
    m["g1_readme"] = int(mt.group(1)) if mt else None

    # Official correlations (data/verify/official_correlations.csv)
    cor = load_csv("data/verify/official_correlations.csv")
    m["corr_official"] = len(cor)
    m["corr_player"] = sum(
        1 for r in cor if re.search(r"player", " ".join(r.values()), re.I)
    )

    # File-name evidence for capture families the repository does not hold
    m["files_inactive"] = count_named(files, r"inactive")
    m["files_snap"] = count_named(files, r"snap[-_]?count")
    m["files_reserve"] = count_named(files, r"reserve")
    m["files_nws"] = count_named(files, r"nws|forecast")
    m["files_roof"] = count_named(files, r"roof")
    m["files_joint"] = count_named(files, r"joint")
    m["files_cluster"] = count_named(files, r"cluster")
    m["pages"] = len([f for f in os.listdir(p("app")) if f.endswith(".html")])

    # Derived values, each defined by a formula over the measured ones above.
    m["lb_fav_roi_pct"] = round(m["lb_fav_roi"] * 100, 1)       # percent, one decimal
    m["g1_short"] = m["g1_gates"] - m["lb_pass_bets"]          # bets still needed by the passing strategy
    m["games3"] = m["games"] * 3                               # opening+closing pairs for 3 markets
    return m


def fill(template: str, m: Dict[str, Any]) -> str:
    def rep(mo: "re.Match[str]") -> str:
        key = mo.group(1)
        if key not in m:
            raise KeyError(f"template key {key!r} is not measured")
        return fmt(m[key])

    return re.sub(r"\{([a-z0-9_]+)\}", rep, template)


# ----------------------------------------------------------------- assembly
def build() -> Dict[str, Any]:
    reg = load_json(REG_PATH)
    gates = load_json(GATES_PATH)
    m = measure()

    rows_out: List[Dict[str, Any]] = []
    spec_rows: Dict[str, Dict[str, Any]] = gates["rows"]
    for r in reg["rows"]:
        spec = spec_rows.get(r["id"], {})
        r4 = spec.get("r4", r["state"])
        if r4 not in STATES:
            raise ValueError(f"{r['id']}: unknown state {r4!r}")
        rows_out.append(
            {
                "id": r["id"],
                "source": "register",
                "category": r["category"],
                "priority": r["priority"],
                "requirement": r["requirement"],
                "register_state": r["state"],
                "r4_state": r4,
                "changed": r4 != r["state"],
                "gate": fill(spec.get("gate", "No blocking gate. The register records this row as met."), m),
                "measured": fill(spec["measured"], m) if spec.get("measured") else "",
                "clears": fill(spec["clears"], m) if spec.get("clears") else "",
                "basis": spec.get("basis", ""),
                "evidence_label": spec.get("ev_label", "repository file"),
                "evidence_url": spec.get("ev") or r.get("evidence_url") or REPO_BLOB + "COORDINATION.md",
            }
        )
    for x in gates["extra"]:
        if x["r4"] not in STATES:
            raise ValueError(f"{x['id']}: unknown state {x['r4']!r}")
        rows_out.append(
            {
                "id": x["id"],
                "source": "round-4 brief item (not in the 2026-11-14 register)",
                "category": x["category"],
                "priority": x["priority"],
                "requirement": x["requirement"],
                "register_state": "not in register",
                "r4_state": x["r4"],
                "changed": False,  # no register state exists to change from
                "gate": fill(x["gate"], m),
                "measured": fill(x["measured"], m),
                "clears": fill(x["clears"], m),
                "basis": x.get("basis", ""),
                "evidence_label": x.get("ev_label", "repository file"),
                "evidence_url": x["ev"],
            }
        )

    ids = [r["id"] for r in rows_out]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate requirement id")

    def counts(key: str) -> Dict[str, int]:
        c = {s: 0 for s in STATES}
        for r in rows_out:
            c[r[key]] = c.get(r[key], 0) + 1
        return c

    flags = [fill(f, m) if isinstance(f, str) else f for f in gates["flags"]]
    for f in flags:
        if isinstance(f, dict):
            for k in ("title", "detail"):
                if k in f:
                    f[k] = fill(f[k], m)
    for r in rows_out:
        if r["changed"] and r["register_state"] != "not in register":
            flags.append(
                {
                    "id": r["id"],
                    "title": f"{r['id']} state changed this round: register '{r['register_state']}' -> '{r['r4_state']}'",
                    "detail": r["gate"],
                    "links": [r["evidence_url"]],
                }
            )

    return {
        "generated_at": ROUND_DATE,
        "session": "arena-fb9e0427-x1",
        "title": "Decision readiness: one row per requirement",
        "brief_source": REPO_BLOB + "docs/live-pipeline/project-brief.md",
        "rule": gates["meta"]["rule"],
        "states": list(STATES),
        "counts": {
            "rows": len(rows_out),
            "register": counts("register_state"),
            "round4": counts("r4_state"),
            "changed": sum(1 for r in rows_out if r["changed"]),
        },
        "measurements": m,
        "rows": rows_out,
        "flags": flags,
    }


def main(argv: List[str]) -> int:
    doc = build()
    text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if "--check" in argv:
        cur = open(p(OUT_PATH), encoding="utf-8").read() if os.path.exists(p(OUT_PATH)) else ""
        if cur != text:
            print(f"STALE: {OUT_PATH} differs from a fresh build. Run tools/build_state_audit.py.")
            return 1
        print(f"ok: {OUT_PATH} matches a fresh build ({doc['counts']['rows']} rows)")
        return 0
    with open(p(OUT_PATH), "w", encoding="utf-8") as fh:
        fh.write(text)
    c = doc["counts"]
    print(f"wrote {OUT_PATH}: {c['rows']} rows; register {c['register']}; round 4 {c['round4']}; changed {c['changed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
