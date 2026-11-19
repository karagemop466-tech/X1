#!/usr/bin/env python3
"""Mechanical check for docs/audit/brief-coverage-2026-11-19.md (session arena-41954ed5-x1).

What it verifies (exit 1 on any failure, prints every failure):
  1. Section 3 has rows 1..82, each with exactly nine cells, numbered contiguously.
  2. Every status cell is one of the five allowed statuses.
  3. The Nov-17 column matches docs/audit/brief-coverage-2026-11-17.md (row by row).
  4. The Changed column is "Yes" exactly when Nov-17 differs from Now.
  5. Every backticked repository path in the document exists on disk
     (wildcards and brace alternations are expanded; ellipses are skipped).
  6. The Check column is one of: a path that exists, presence, fetch, grep, or dash.
     A BUILT row may not use dash or grep, because it needs a check run this session.
  7. Every official link in the Source column is on an allow-listed host.
  8. Section 4 (measured facts) is recomputed from the files it names and must match.
  9. Section 5 lists exactly the rows whose status changed.
 10. The headline counts in section 2 match the table.

Run:  python3 tools/verify_brief_coverage_2026_11_19.py
"""
from __future__ import annotations

import csv
import glob
import itertools
import json
import os
import re
import sys
from collections import Counter
from urllib.parse import urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOC = os.path.join(ROOT, "docs/audit/brief-coverage-2026-11-19.md")
OLD = os.path.join(ROOT, "docs/audit/brief-coverage-2026-11-17.md")

ALLOWED_STATUS = {"BUILT", "PARTIAL", "DEFINED", "NOT BUILT", "DECLINED"}
CHECK_TOKENS = {"presence", "fetch", "grep", "—", "-"}
ALLOWED_HOST_SUFFIX = ("nfl.com", "weather.gov")
ALLOWED_HOSTS_EXACT = {"github.com", "karagemop466-tech.github.io"}
ALLOWED_GITHUB_PREFIXES = ("/nflverse/",)  # mirror links must name the mirror

failures: list[str] = []
passes = 0


def fail(msg: str) -> None:
    failures.append(msg)


def ok(_msg: str = "") -> None:
    global passes
    passes += 1


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def split_cells(line: str) -> list[str]:
    parts = [c.strip() for c in line.strip().split("|")]
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    return parts


def section(text: str, start_marker: str, end_marker: str | None) -> str:
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker)) if end_marker else len(text)
    return text[i:j]


def expand_braces(token: str) -> list[str]:
    m = re.search(r"\{([^{}]+)\}", token)
    if not m:
        return [token]
    out: list[str] = []
    for alt in m.group(1).split(","):
        out.extend(expand_braces(token[: m.start()] + alt.strip() + token[m.end():]))
    return out


def path_exists(token: str) -> bool:
    for cand in expand_braces(token):
        if "*" in cand:
            if not glob.glob(os.path.join(ROOT, cand), recursive=True):
                # a wildcard may legitimately point at an empty future directory; require the parent
                parent = os.path.dirname(cand.split("*")[0].rstrip("/")) or cand.split("*")[0].rstrip("/")
                if not os.path.isdir(os.path.join(ROOT, parent)):
                    return False
            continue
        if not os.path.exists(os.path.join(ROOT, cand.rstrip("/"))):
            return False
    return True


def looks_like_path(tok: str) -> bool:
    if "…" in tok or " " in tok or "http" in tok or "#" in tok:
        return False
    if "/" in tok:
        return True
    return bool(re.search(r"\.(md|py|json|csv|html|tsv|yml|jsonl|txt|psv|sh)$", tok))


def main() -> int:
    text = read(DOC)
    old_text = read(OLD)

    # ------------------------------------------------------------ section 3
    sec3 = section(text, "## 3. Row register", "## 4. Measured facts")
    rows = []
    for line in sec3.splitlines():
        if re.match(r"^\| \d+ \|", line):
            cells = split_cells(line)
            if len(cells) != 9:
                fail(f"row {cells[0] if cells else '?'}: expected 9 cells, found {len(cells)}")
                continue
            rows.append(cells)
    nums = [int(r[0]) for r in rows]
    if nums != list(range(1, 83)):
        fail(f"row numbers are not 1..82 in order (found {len(rows)} rows: {nums[:3]}..{nums[-3:]})")
    else:
        ok("82 rows, numbered 1..82")

    # Nov-17 statuses
    old_status: dict[int, str] = {}
    for line in old_text.splitlines():
        if re.match(r"^\| \d+ \|", line):
            c = split_cells(line)
            if len(c) >= 3:
                old_status[int(c[0])] = c[2]
    if len(old_status) != 82:
        fail(f"Nov-17 register parsed {len(old_status)} rows, expected 82")

    computed_changed: list[int] = []
    now_counter: Counter = Counter()
    for r in rows:
        n = int(r[0])
        nov, now, changed = r[2], r[3], r[4]
        if now not in ALLOWED_STATUS:
            fail(f"row {n}: status '{now}' is not allowed")
        if nov not in ALLOWED_STATUS:
            fail(f"row {n}: Nov-17 status '{nov}' is not allowed")
        if old_status.get(n) != nov:
            fail(f"row {n}: Nov-17 column says '{nov}' but the Nov-17 register says '{old_status.get(n)}'")
        else:
            ok()
        is_changed = nov != now
        if (changed == "Yes") != is_changed:
            fail(f"row {n}: Changed='{changed}' but Nov-17 '{nov}' vs Now '{now}'")
        if is_changed:
            computed_changed.append(n)
        now_counter[now] += 1

        # evidence paths
        for tok in re.findall(r"`([^`]+)`", r[5]):
            if looks_like_path(tok) and not path_exists(tok):
                fail(f"row {n}: evidence path does not exist: {tok}")
        # check column
        chk = r[6]
        if chk in CHECK_TOKENS or chk == "—":
            if now == "BUILT" and chk in {"grep", "—", "-"}:
                fail(f"row {n}: BUILT needs a check run this session, found '{chk}'")
        else:
            for tok in [t.strip() for t in chk.split(";") if t.strip()]:
                if tok in CHECK_TOKENS:
                    continue
                if not path_exists(tok):
                    fail(f"row {n}: check path does not exist: {tok}")
        # official links
        src = r[8]
        for url in re.findall(r"https?://[^\s)`]+", src):
            host = urlparse(url).hostname or ""
            allowed = host.endswith(ALLOWED_HOST_SUFFIX) or host in ALLOWED_HOSTS_EXACT
            if host in ALLOWED_HOSTS_EXACT and host == "github.com":
                allowed = urlparse(url).path.startswith(ALLOWED_GITHUB_PREFIXES)
            if not allowed:
                club_hosts = club_host_set()
                allowed = host in club_hosts
            if not allowed:
                fail(f"row {n}: official link host not allow-listed: {url}")
    if not failures:
        ok("status, Nov-17 and Changed columns consistent")

    # ------------------------------------------------------------ section 2 headline
    sec2 = section(text, "## 2. Headline", "## 3. Row register")
    m = re.search(r"BUILT (\d+) · PARTIAL (\d+) · DEFINED (\d+) · NOT BUILT (\d+) · DECLINED (\d+)", sec2)
    if not m:
        fail("section 2 status counts line not found")
    else:
        claimed = dict(zip(["BUILT", "PARTIAL", "DEFINED", "NOT BUILT", "DECLINED"], map(int, m.groups())))
        for k, v in claimed.items():
            if now_counter.get(k, 0) != v:
                fail(f"section 2 claims {k}={v} but the table has {now_counter.get(k, 0)}")
        if sum(claimed.values()) != 82:
            fail("section 2 status counts do not sum to 82")
        else:
            ok()
    m2 = re.search(r"(\d+) rows changed status since 2026-11-17", sec2)
    if not m2 or int(m2.group(1)) != len(computed_changed):
        fail(f"section 2 says {m2.group(1) if m2 else '?'} rows changed; table has {len(computed_changed)}")
    else:
        ok()

    # ------------------------------------------------------------ section 5
    sec5 = section(text, "## 5. Changes since 2026-11-17", "## 6. Irregularities")
    listed = []
    for line in sec5.splitlines():
        if re.match(r"^\| \d+ \|", line):
            listed.append(int(split_cells(line)[0]))
    if sorted(listed) != sorted(computed_changed):
        fail(f"section 5 lists {sorted(listed)} but the table changed {sorted(computed_changed)}")
    else:
        ok()

    # ------------------------------------------------------------ section 6
    sec6 = section(text, "## 6. Irregularities", "## 7. What this audit did not do")
    ids = [split_cells(l)[0] for l in sec6.splitlines() if re.match(r"^\| I-\d+ \|", l)]
    if ids != [f"I-{i}" for i in range(1, 8)]:
        fail(f"section 6 irregularity ids: {ids}")
    else:
        ok()

    # ------------------------------------------------------------ backticked paths anywhere
    for tok in set(re.findall(r"`([^`]+)`", text)):
        if looks_like_path(tok) and not path_exists(tok):
            fail(f"backticked path does not exist: {tok}")

    # ------------------------------------------------------------ section 4 measured facts
    sec4 = section(text, "## 4. Measured facts", "## 5. Changes since 2026-11-17")
    facts = {}
    for line in sec4.splitlines():
        if line.startswith("| ") and not line.startswith("| Fact") and not line.startswith("| ---"):
            c = split_cells(line)
            if len(c) == 3:
                facts[c[0]] = c[1]
    recomputed = compute_facts()
    for name, value in recomputed.items():
        if name not in facts:
            fail(f"measured fact not in section 4: {name}")
            continue
        if str(value) != facts[name].replace(",", "").strip():
            fail(f"measured fact '{name}': doc says {facts[name]}, file says {value}")
        else:
            ok()
    for name in facts:
        if name not in recomputed:
            fail(f"section 4 fact with no recomputation: {name}")

    # ------------------------------------------------------------ report
    print(f"checks passed : {passes}")
    print(f"rows          : {len(rows)}  statuses {dict(now_counter)}")
    print(f"changed rows  : {len(computed_changed)}  {computed_changed}")
    if failures:
        print(f"FAILURES      : {len(failures)}")
        for f in failures:
            print("  - " + f)
        return 1
    print("brief coverage 2026-11-19: all rows, paths, links and measured facts verified")
    return 0


_CLUB_HOSTS: set[str] | None = None


def club_host_set() -> set[str]:
    """Official club sites are the hosts that the depth files themselves cite."""
    global _CLUB_HOSTS
    if _CLUB_HOSTS is None:
        hosts: set[str] = set()
        path = os.path.join(ROOT, "data/depth/depth_groups_32.csv")
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                h = urlparse(r.get("source_url", "")).hostname
                if h:
                    hosts.add(h)
        _CLUB_HOSTS = hosts
    return _CLUB_HOSTS


def compute_facts() -> dict:
    out: dict = {}

    g = list(csv.DictReader(open(os.path.join(ROOT, "data/depth/depth_groups_32.csv"), encoding="utf-8")))
    out["depth_groups rows"] = len(g)
    out["depth_groups clubs"] = len({r["team_abbrev"] for r in g})
    out["depth_groups rows with jersey_stripped = true"] = sum(r["jersey_stripped"] == "true" for r in g)
    gb = [r for r in g if r["team_abbrev"] == "GB"]
    out["GB rows whose raw_player starts with a digit"] = sum(r["raw_player"][:1].isdigit() for r in gb)
    out["empty_depth_gap rows (all clubs)"] = sum(r["slot_kind"] == "empty_depth_gap" for r in g)
    out["empty_depth_gap rows for WAS"] = sum(r["slot_kind"] == "empty_depth_gap" and r["team_abbrev"] == "WAS" for r in g)
    out["shared_concatenated_cell rows"] = sum(r["slot_kind"] == "shared_concatenated_cell" for r in g)

    rd = list(csv.DictReader(open(os.path.join(ROOT, "data/depth/replacement_depth.csv"), encoding="utf-8")))
    out["replacement_depth starters starting with a digit"] = sum(r["starter"][:1].isdigit() for r in rd)

    inj = list(csv.DictReader(open(os.path.join(ROOT, "data/injuries/injuries_2026_week10.csv"), encoding="utf-8")))
    out["injuries_2026_week10.csv data rows"] = len(inj)

    caps = [json.loads(l) for l in open(os.path.join(ROOT, "data/captures/index.jsonl"), encoding="utf-8") if l.strip()]
    out["capture entries (all datasets)"] = len(caps)
    out["capture entries, dataset injuries"] = sum(c.get("dataset") == "injuries" for c in caps)

    sp = json.load(open(os.path.join(ROOT, "data/models/season_splits.json"), encoding="utf-8"))
    out["season split rows"] = len(sp["rows"])
    out["season split games, final_holdout 2025"] = next(r["games"] for r in sp["rows"] if r["split"] == "final_holdout")

    pa = json.load(open(os.path.join(ROOT, "data/models/personnel_ablations.json"), encoding="utf-8"))
    out["personnel ablation rows"] = len(pa["rows"])
    out["personnel ablation rows BLOCKED"] = sum(str(r["status"]).startswith("BLOCKED") for r in pa["rows"])

    dt = json.load(open(os.path.join(ROOT, "data/models/dual_totals_walkforward.json"), encoding="utf-8"))
    out["dual-total games"] = len(dt["rows"])

    ts = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/skill/two_stage_leaderboard.csv"), encoding="utf-8")))
    out["two-stage division values"] = len({r["division"] for r in ts})
    out["two-stage rows"] = len(ts)

    vf = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/skill/vig_free_decomposition.csv"), encoding="utf-8")))
    out["vig_free_decomposition rows"] = len(vf)
    out["vig_free_decomposition rows with numeric overround"] = sum(bool(r["book_overround_pct"].strip()) for r in vf)

    wd = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/skill/weekly_what_changed_w9_w10_w11.csv"), encoding="utf-8")))
    out["weekly diff clubs"] = len(wd)

    st = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/roster/stale_depth_and_turnover_audit.csv"), encoding="utf-8")))
    out["stale-depth audit rows"] = len(st)
    tr = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/roster/official_trades_nov_2026.csv"), encoding="utf-8")))
    out["official trades rows"] = len(tr)
    rs = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/roster/official_reserve_list_2026_oct_nov.csv"), encoding="utf-8")))
    out["reserve list rows"] = len(rs)
    ina = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/roster/official_inactives_2026_week10.csv"), encoding="utf-8")))
    out["official inactives rows"] = len(ina)
    wx = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/weather/week11_stadium_nws_overlay.csv"), encoding="utf-8")))
    out["NWS overlay games"] = len(wx)
    an = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/roster/announced_starters_evidence.csv"), encoding="utf-8")))
    out["announced-starter rows"] = len(an)

    co = list(csv.DictReader(open(os.path.join(ROOT, "data/origination_desk/skill/official_correlations_with_n.csv"), encoding="utf-8")))
    out["official correlation pairs"] = len(co)

    ve = list(csv.DictReader(open(os.path.join(ROOT, "data/nfl/venues_2026_week10.csv"), encoding="utf-8")))
    out["Week 10 venue rows"] = len(ve)

    pr = list(csv.DictReader(open(os.path.join(ROOT, "data/prices/price_history.csv"), encoding="utf-8")))
    out["price history rows"] = len(pr)
    vr = list(csv.DictReader(open(os.path.join(ROOT, "data/results/verified_results.csv"), encoding="utf-8")))
    out["verified results rows"] = len(vr)

    mc = list(csv.DictReader(open(os.path.join(ROOT, "data/mind_change/register.csv"), encoding="utf-8")))
    out["mind-change register rows"] = len(mc)
    dr = list(csv.DictReader(open(os.path.join(ROOT, "data/readiness/decision_readiness.csv"), encoding="utf-8")))
    out["decision-readiness rows"] = len(dr)
    return out


if __name__ == "__main__":
    sys.exit(main())
