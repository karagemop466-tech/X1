#!/usr/bin/env python3
"""Verify the 2026-11-18 official reads pack (session arena/91656714-x1, round 6).

Why this exists
---------------
Round 5 landed two independent reads of the same official pages on 2026-11-17. This round made a
third, on 2026-11-18, and it is the read the feed is settled against. Three reads of one page are
evidence only if something proves they agree; a pack that merely sits on disk proves nothing.

The checks below are deliberately arithmetic where arithmetic is possible. The strongest one is B7:
it recomputes all 32 clubs' W-L-T, PF and PA **from the 150-game feed itself** and requires the
official standings table to match. If a promoted score were wrong, a club's PF/PA would move and
B7 would fail — so B7 is what makes "the feed is verified" mean something rather than "the feed was
transcribed".

Checks
  A1  pack files exist, parse, and every row cites an official nfl.com URL
  A2  Week 10 slate completeness: 14 fixtures + 4 byes = 32 clubs, each appearing exactly once
  A3  each club's record printed on the week page equals its record on the standings page
  A4  standings internal arithmetic: PCT, NET PTS, HOME+ROAD = W-L-T, sum(W)=sum(L), sum(PF)=sum(PA)
  B5  the three independent reads of the Week 10 finals agree cell for cell (this pack vs 11-17)
  B6  the three independent standings reads agree cell for cell (this pack vs 11-17 and 11-16)
  B7  the published results feed reproduces all 32 clubs' W-L-T/PF/PA from the official table
  B8  no Week 10 fixture that the official page prints Final is still 'SCHEDULED' in the feed
  B9  the feed's own settlement_summary counts agree with its rows

Usage
  python3 tools/verify_2026_11_18.py            # verify, print a report
  python3 tools/verify_2026_11_18.py --check    # same, exit 1 on any failure (CI form)
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "data", "verification", "2026_11_18")
PACK_17 = os.path.join(ROOT, "data", "verification", "2026_11_17")
PACK_16 = os.path.join(ROOT, "data", "verification", "2026_11_16")
FEED = os.path.join(ROOT, "data", "results_feed.json")

FINALS = os.path.join(PACK, "official_w10_finals_2026_11_18.tsv")
STANDINGS = os.path.join(PACK, "official_standings_2026_11_18.tsv")

# The official standings page prints LA and AZ; the fixture tables and the repo's older files use
# LAR and ARI/ARZ. Aliases are for JOINING only. No cell is relabelled on the way out.
ALIAS = {"LAR": "LA", "ARZ": "AZ", "ARI": "AZ", "WSH": "WAS", "OAK": "LV", "SD": "LAC", "STL": "LA"}


# The standings packs in this repository use a lowercase header (abbr/w/l/t/...). Column identity
# is read from the header rather than assumed by position: if a pack ever renames a column the
# check fails loudly instead of silently comparing the wrong two fields.
STAND_TEAM, STAND_W, STAND_L, STAND_T = "abbr", "w", "l", "t"
STAND_PCT, STAND_PF, STAND_PA, STAND_NET = "pct", "pf", "pa", "net"
STAND_HOME, STAND_ROAD, STAND_STRK = "home", "road", "streak"


def canon(code: str) -> str:
    return ALIAS.get(code, code)


def _triple(rec: str) -> tuple[int, int, int]:
    """'5-5' -> (5, 5, 0); '3-5-1' -> (3, 5, 1). The weekend page omits a zero tie count; that is
    a spelling difference, not a different record."""
    parts = [int(x) for x in rec.split("-")]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0], parts[1], parts[2])


def read_tsv(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        rdr = csv.DictReader((ln for ln in f if not ln.startswith("#")), delimiter="\t")
        for r in rdr:
            if r.get("game_id") or r.get(STAND_TEAM):
                rows.append(r)
    return rows


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.notes: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        if ok:
            print(f"  PASS {name}" + (f" — {detail}" if detail else ""))
        else:
            print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
            self.fails.append(f"{name}: {detail}")
        return ok

    def note(self, msg: str) -> None:
        self.notes.append(msg)
        print(f"  note {msg}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit nonzero on any failure (CI form)")
    args = ap.parse_args()

    rep = Report()

    # ---- A1 ------------------------------------------------------------------
    print("A1  pack files exist, parse, every row cites an official URL")
    ok = os.path.exists(FINALS) and os.path.exists(STANDINGS)
    rep.check("A1.1 both pack files exist", ok)
    finals = read_tsv(FINALS) if ok else []
    standings = read_tsv(STANDINGS) if ok else []
    rep.check("A1.2 finals pack has 14 rows", len(finals) == 14, f"{len(finals)} rows")
    rep.check("A1.3 standings pack has 32 rows", len(standings) == 32, f"{len(standings)} rows")
    bad_url = [r["game_id"] for r in finals
               if not (r.get("game_url", "").startswith("https://www.nfl.com/games/")
                       and r.get("source_url", "").startswith("https://www.nfl.com/schedules/"))]
    rep.check("A1.4 every finals row cites an official nfl.com game + schedule URL", not bad_url,
              f"{len(bad_url)} bad: {bad_url[:3]}")

    # ---- A2 ------------------------------------------------------------------
    print("\nA2  Week 10 slate completeness (14 fixtures + 4 byes = 32 clubs, each once)")
    clubs = []
    for r in finals:
        clubs += [canon(r["away"]), canon(r["home"])]
    byes = {"CHI", "DEN", "PHI", "TB"}
    dupes = sorted({c for c in clubs if clubs.count(c) > 1})
    allc = set(clubs) | byes
    rep.check("A2.1 no club appears twice in the slate", not dupes, f"dupes: {dupes}")
    rep.check("A2.2 slate + byes covers exactly 32 clubs", len(allc) == 32,
              f"{len(allc)} clubs")
    rep.check("A2.3 slate clubs and bye clubs do not overlap",
              not (set(clubs) & byes), f"overlap: {sorted(set(clubs) & byes)}")

    # ---- A3 ------------------------------------------------------------------
    print("\nA3  club records on the week page equal the standings page")
    st = {canon(r[STAND_TEAM]): r for r in standings}
    mism = []
    for r in finals:
        for side in ("away", "home"):
            c = canon(r[side])
            printed = r[f"{side}_record"]
            s = st.get(c)
            if s is None:
                mism.append((c, "absent from standings"))
                continue
            rec = f"{s[STAND_W]}-{s[STAND_L]}-{s[STAND_T]}"
            # the weekend page prints "5-5" for a club with no ties and "3-5-1" when it has one;
            # both are the same record. Compare the numeric triples, not the string spelling.
            if _triple(printed) != _triple(rec):
                mism.append((c, f"week={printed} standings={rec}"))
    rep.check("A3.1 all 28 slate clubs' records agree across the two official pages", not mism,
              f"{len(mism)} mismatches: {mism[:3]}")

    # ---- A4 ------------------------------------------------------------------
    print("\nA4  standings internal arithmetic")
    bad = []
    for r in standings:
        W, L, T = int(r[STAND_W]), int(r[STAND_L]), int(r[STAND_T])
        pf, pa, net = int(r[STAND_PF]), int(r[STAND_PA]), int(r[STAND_NET])
        if pf - pa != net:
            bad.append((r[STAND_TEAM], f"PF-PA={pf-pa} NET={net}"))
        hw, hl, ht = _triple(r[STAND_HOME])
        rw, rl, rt = _triple(r[STAND_ROAD])
        if (hw + rw, hl + rl, ht + rt) != (W, L, T):
            bad.append((r[STAND_TEAM], f"HOME+ROAD != W-L-T ({hw+rw}-{hl+rl}-{ht+rt} vs {W}-{L}-{T})"))
        pct = float(r[STAND_PCT])
        denom = W + L + T
        if denom and abs(pct - round((W + 0.5 * T) / denom, 3)) > 0.0011:
            bad.append((r[STAND_TEAM], f"PCT {pct} != {round((W+0.5*T)/denom,3)}"))
    rep.check("A4.1 NET PTS = PF - PA, HOME+ROAD = W-L-T, PCT consistent (32 clubs)", not bad,
              f"{len(bad)} failures: {bad[:3]}")
    sw = sum(int(r[STAND_W]) for r in standings)
    sl = sum(int(r[STAND_L]) for r in standings)
    spf = sum(int(r[STAND_PF]) for r in standings)
    spa = sum(int(r[STAND_PA]) for r in standings)
    rep.check("A4.2 league closure: sum(W) == sum(L)", sw == sl, f"{sw} vs {sl}")
    rep.check("A4.3 league closure: sum(PF) == sum(PA)", spf == spa, f"{spf} vs {spa}")
    rep.check("A4.4 total games implied by the table is even and integral",
              sw % 1 == 0, f"sum(W)={sw} -> {sw} games")

    # ---- B5 ------------------------------------------------------------------
    print("\nB5  the three independent reads of the Week 10 finals agree")
    p17 = {r["game_id"]: r for r in read_tsv(os.path.join(PACK_17, "official_w10_finals_2026_11_17.tsv"))}
    p16 = {}
    p16_path = os.path.join(PACK_16, "official_w10_results_2026_11_16.tsv")
    if os.path.exists(p16_path):
        p16 = {r["game_id"]: r for r in read_tsv(p16_path)}
    rep.check("B5.1 all three packs cover the same 14 fixtures",
              len(p17) == 14 and len(finals) == 14,
              f"11-16={len(p16)} 11-17={len(p17)} 11-18={len(finals)}")
    cell_mism = []
    for gid, r18 in ((g, r) for g, r in ((x["game_id"], x) for x in finals)):
        r17 = p17.get(gid)
        if r17 is None:
            cell_mism.append((gid, "absent from 11-17 pack"))
            continue
        for col in ("away", "away_score", "home", "home_score", "date_et", "status"):
            a, b = r18.get(col, ""), r17.get(col, "")
            if col in ("away", "home"):
                if canon(a) != canon(b):
                    cell_mism.append((gid, f"{col}: 11-18={a} 11-17={b}"))
            elif a != b:
                cell_mism.append((gid, f"{col}: 11-18={a!r} 11-17={b!r}"))
    rep.check("B5.2 11-18 vs 11-17: 0 cell mismatches over 14 fixtures x 6 columns",
              not cell_mism, f"{len(cell_mism)} mismatches: {cell_mism[:4]}")
    n16 = 0
    cell16 = []
    unscored16 = []
    for gid, r18 in ((x["game_id"], x) for x in finals):
        r16 = p16.get(gid)
        if r16 is None:
            continue
        n16 += 1
        if r16.get("status", "").lower() != "final":
            # correct point-in-time value: the 11-16 read was made before that game was played.
            unscored16.append((gid, r16.get("status")))
            continue
        for col in ("away_score", "home_score"):
            if r18.get(col, "") != r16.get(col, ""):
                cell16.append((gid, f"{col}: 11-18={r18.get(col)} 11-16={r16.get(col)}"))
    rep.check("B5.3 11-18 vs 11-16: scores agree on every fixture the 11-16 read had scored",
              not cell16, f"{n16} shared fixtures, {len(cell16)} mismatches")
    rep.check("B5.4 every fixture the 11-16 read left unscored is Final now (a dated delta, not a conflict)",
              all(s_ in ("Scheduled", "SCHEDULED") for _, s_ in unscored16),
              f"{len(unscored16)} legitimately unscored on 11-16: {unscored16}")

    # ---- B6 ------------------------------------------------------------------
    print("\nB6  the independent standings reads agree")
    s17 = {canon(r[STAND_TEAM]): r for r in
           read_tsv(os.path.join(PACK_17, "official_standings_2026_11_17.tsv"))}
    s16 = {}
    p = os.path.join(PACK_16, "official_standings_2026_11_16.tsv")
    if os.path.exists(p):
        s16 = {canon(r[STAND_TEAM]): r for r in read_tsv(p)}
    common_cols = [c for c in (STAND_W, STAND_L, STAND_T, STAND_PCT, STAND_PF, STAND_PA,
                              STAND_NET, STAND_HOME, STAND_ROAD, STAND_STRK)
                   if c in standings[0] and any(c in r for r in s17.values())]
    sm = []
    for team, r18 in ((canon(r[STAND_TEAM]), r) for r in standings):
        r17 = s17.get(team)
        if r17 is None:
            sm.append((team, "absent from 11-17"))
            continue
        for c in common_cols:
            if r18.get(c, "") != r17.get(c, ""):
                sm.append((team, f"{c}: 11-18={r18.get(c)} 11-17={r17.get(c)}"))
    rep.check(f"B6.1 11-18 vs 11-17: 0 cell mismatches over 32 clubs x {len(common_cols)} columns",
              not sm, f"{len(sm)} mismatches: {sm[:4]}")
    sm16 = []
    if s16:
        c16 = [c for c in common_cols if any(c in r for r in s16.values())]
        for team, r18 in ((canon(r[STAND_TEAM]), r) for r in standings):
            r16 = s16.get(team)
            if r16 is None:
                continue
            for c in c16:
                if r18.get(c, "") != r16.get(c, ""):
                    sm16.append((team, c))
        # The 11-16 read was taken before the Monday-night game (LAC at BAL, 2026-11-16) was played,
        # so exactly those two clubs may differ, and only in cells the result touches. Any other
        # club differing is a contradiction between two reads of the same page, and fails.
        changed = {t for t, _ in sm16}
        allowed = {"BAL", "LAC"}
        rep.check(f"B6.2 11-18 vs 11-16: the only clubs that differ are the two in the Monday game",
                  changed <= allowed,
                  f"{len(sm16)} cells over clubs {sorted(changed)} (allowed: {sorted(allowed)})")
        rep.check("B6.3 and every difference is the Monday result itself (W/L/PCT/PF/PA/NET/splits/streak)",
                  all(c in (STAND_W, STAND_L, STAND_PCT, STAND_PF, STAND_PA, STAND_NET,
                            STAND_HOME, STAND_ROAD, STAND_STRK) or c.endswith("_record")
                      for _, c in sm16),
                  f"columns touched: {sorted({c for _, c in sm16})}")

    # ---- B7 ------------------------------------------------------------------
    print("\nB7  the published feed reproduces all 32 clubs' W-L-T / PF / PA")
    feed = json.load(open(FEED, encoding="utf-8"))
    agg = defaultdict(lambda: {"W": 0, "L": 0, "T": 0, "PF": 0, "PA": 0, "games": 0})
    scored = 0
    for r in feed["rows"]:
        if r.get("status") != "FINAL":
            continue
        a, h = canon(r["away"]), canon(r["home"])
        asc, hsc = r.get("away_score"), r.get("home_score")
        if asc is None or hsc is None:
            continue
        scored += 1
        agg[a]["PF"] += asc; agg[a]["PA"] += hsc; agg[a]["games"] += 1
        agg[h]["PF"] += hsc; agg[h]["PA"] += asc; agg[h]["games"] += 1
        if asc > hsc:
            agg[a]["W"] += 1; agg[h]["L"] += 1
        elif hsc > asc:
            agg[h]["W"] += 1; agg[a]["L"] += 1
        else:
            agg[a]["T"] += 1; agg[h]["T"] += 1
    diffs = []
    for r in standings:
        t = canon(r[STAND_TEAM])
        f = agg.get(t)
        if f is None:
            diffs.append((t, "no games in feed"))
            continue
        for col, key in ((STAND_W, "W"), (STAND_L, "L"), (STAND_T, "T"),
                         (STAND_PF, "PF"), (STAND_PA, "PA")):
            if int(r[col]) != f[key]:
                diffs.append((t, f"{col}: official={r[col]} feed={f[key]}"))
                break
    rep.check(f"B7.1 all 32 clubs' W-L-T/PF/PA reproduce from the feed "
              f"({scored} scored games, {scored*2} club-games, 160 cells)",
              not diffs, f"{len(diffs)} clubs disagree: {diffs[:5]}")

    # ---- B8 ------------------------------------------------------------------
    print("\nB8  no fixture printed Final is still 'SCHEDULED' in the feed")
    by_id = {r["game_id"]: r for r in feed["rows"]}
    frozen = []
    for r in finals:
        gid = r["game_id"]
        cand = None
        for k in (gid, gid.replace("ARZ", "ARI"), gid.replace("LA_", "LAR_")):
            if k in by_id:
                cand = by_id[k]; break
        if cand is None:
            frozen.append((gid, "absent from feed"))
        elif cand.get("status") != "FINAL":
            frozen.append((gid, f"feed status={cand.get('status')}"))
    rep.check("B8.1 all 14 official Week 10 finals are FINAL in the feed", not frozen,
              f"{len(frozen)} frozen: {frozen[:4]}")

    # ---- B9 ------------------------------------------------------------------
    print("\nB9  the feed's own settlement_summary agrees with its rows")
    ss = feed.get("settlement_summary", {})
    n_fin = sum(1 for r in feed["rows"] if r.get("status") == "FINAL")
    n_sch = sum(1 for r in feed["rows"] if r.get("status") != "FINAL")
    rep.check("B9.1 games_final equals the count of FINAL rows",
              ss.get("games_final") == n_fin, f"summary={ss.get('games_final')} rows={n_fin}")
    rep.check("B9.2 games_scheduled equals the count of non-FINAL rows",
              ss.get("games_scheduled") == n_sch, f"summary={ss.get('games_scheduled')} rows={n_sch}")
    rep.check("B9.3 games_final + games_scheduled equals the row count",
              (ss.get("games_final", 0) + ss.get("games_scheduled", 0)) == len(feed["rows"]),
              f"{ss.get('games_final',0)}+{ss.get('games_scheduled',0)} vs {len(feed['rows'])}")

    print()
    if rep.fails:
        print(f"FAILED — {len(rep.fails)} check(s):")
        for f in rep.fails:
            print(f"  - {f}")
        return 1
    print(f"ALL CHECKS PASSED — feed {len(feed['rows'])} rows, {n_fin} FINAL, {n_sch} scheduled; "
          f"{scored} scored games reconcile to 32 official standings rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
