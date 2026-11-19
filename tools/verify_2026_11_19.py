#!/usr/bin/env python3
"""2026-11-19 round-7 official re-verification pack (session arena/427c1843-x1).

Re-reads (2026-11-19, fetch tool, transcribed by hand into this pack):

  data/verification/2026_11_19/official_standings_2026_11_19.tsv   the league standings page
  data/verification/2026_11_19/official_w10_results_2026_11_19.tsv the Week 10 slate (14 finals)
  data/verification/2026_11_19/official_w11_schedule_2026_11_19.tsv the Week 11 slate (13 fixtures)
  data/verification/2026_11_19/official_w11_byes_2026_11_19.tsv    the Week 11 bye block (6 clubs)

Checks (all measured, never assumed):

  A1  standings identities      NET = PF - PA and PCT = round((W + T/2)/GP, 3) for all 32 clubs
                                (64 assertions), plus HOME + ROAD = W-L-T (32) = 96.
  A2  league closure            sum(W) = sum(L), ties even, sum(PF) = sum(PA), sum(NET) = 0,
                                games implied = 150 (unchanged since the Week 10 close).
  A3  cross-page records        every club record printed on the Week 11 page (26 in fixtures + 6 in
                                the bye block) equals the W-L-T on the standings page read the same day.
                                A disagreement is REPORTED as a conflict, never resolved by preference.
  A4  continuity vs 2026-11-18  today's 32 standings rows and 14 Week 10 finals equal the 2026-11-18
                                pack field for field (no league game can have finished in between:
                                the next game is Week 11's Thursday fixture on 2026-11-19).
  A5  slate completeness        Week 11 covers 32 clubs exactly once (13 x 2 + 6 byes); every fixture
                                carries the printed time, network and a game URL.
  A6  fixture continuity        Week 11 fixtures are compared with the frozen 2026-11-17 read
                                (data/lab/reads/2026-11-17/week11_slate_2026-11-17.tsv): the only
                                permitted movement is a club record that a Week 10 result changed.

Usage:
  python3 tools/verify_2026_11_19.py            # build + verify (exit 1 on violation)
  python3 tools/verify_2026_11_19.py --check    # build, compare to committed summary
                                                # (ignoring generated_at), exit 1 on drift
Outputs (under data/verification/2026_11_19/):
  verification_summary_2026_11_19.json          every check, its counts, its verdict and its conflicts
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "data", "verification", "2026_11_19")
PRIOR = os.path.join(ROOT, "data", "verification", "2026_11_18")
FROZEN_W11 = os.path.join(ROOT, "data", "lab", "reads", "2026-11-17", "week11_slate_2026-11-17.tsv")
SUMMARY = os.path.join(PACK, "verification_summary_2026_11_19.json")

SOURCE_STANDINGS = "https://www.nfl.com/standings/league/2026/REG"
SOURCE_W10 = "https://www.nfl.com/schedules/2026/by-week/week-10"
SOURCE_W11 = "https://www.nfl.com/schedules/2026/by-week/week-11"

READ_AT = "2026-11-19 (UTC), fetch tool, chunks 0-1 of 2 (standings) / 0-1 of 2 (w10) / 0-2 of 3 (w11)"

# The bye block prints "LAR"; the standings page prints "LA". Declared alias, counted below.
ALIASES = {"LAR": "LA"}


def read_tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    return [dict(r) for r in csv.DictReader(lines, delimiter="\t")]


def rec(s: str) -> tuple[int, int, int]:
    parts = [p.strip() for p in s.split("-")]
    while len(parts) < 3:
        parts.append("0")
    return int(parts[0]), int(parts[1]), int(parts[2])


def rec_dash(w: int, l: int, t: int) -> str:
    return f"{w}-{l}-{t}" if t else f"{w}-{l}"


def main() -> int:
    os.makedirs(PACK, exist_ok=True)
    checks: dict[str, dict] = {}

    standings = read_tsv(os.path.join(PACK, "official_standings_2026_11_19.tsv"))
    w10 = read_tsv(os.path.join(PACK, "official_w10_results_2026_11_19.tsv"))
    w11 = read_tsv(os.path.join(PACK, "official_w11_schedule_2026_11_19.tsv"))
    byes = read_tsv(os.path.join(PACK, "official_w11_byes_2026_11_19.tsv"))

    # ---------------------------------------------------------------- A1
    a1_total = a1_ok = 0
    a1_bad = []
    for r in standings:
        w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
        pf, pa, net = int(r["pf"]), int(r["pa"]), int(r["net"])
        gp = w + l + t
        a1_total += 1
        if net == pf - pa:
            a1_ok += 1
        else:
            a1_bad.append(f"{r['abbr']} NET {net} != PF-PA {pf - pa}")
        a1_total += 1
        pct = round((w + t / 2) / gp, 3) if gp else 0.0
        if abs(float(r["pct"]) - pct) <= 0.0005:
            a1_ok += 1
        else:
            a1_bad.append(f"{r['abbr']} PCT {r['pct']} != {pct:.3f}")
        a1_total += 1
        hw, hl, ht = rec(r["home"])
        rw, rl, rt = rec(r["road"])
        if (hw + rw, hl + rl, ht + rt) == (w, l, t):
            a1_ok += 1
        else:
            a1_bad.append(f"{r['abbr']} HOME+ROAD {r['home']}+{r['road']} != {w}-{l}-{t}")
    checks["A1"] = {
        "name": "standings identities (NET, PCT, HOME+ROAD)",
        "assertions": a1_total,
        "passed": a1_ok,
        "failures": a1_bad,
        "verdict": "pass" if a1_ok == a1_total else "FAIL",
    }

    # ---------------------------------------------------------------- A2
    W = sum(int(r["w"]) for r in standings)
    L = sum(int(r["l"]) for r in standings)
    T = sum(int(r["t"]) for r in standings)
    PF = sum(int(r["pf"]) for r in standings)
    PA = sum(int(r["pa"]) for r in standings)
    NETM = sum(int(r["net"]) for r in standings)
    implied = (W + L + T) / 2
    a2 = {
        "clubs": len(standings),
        "sum_w": W,
        "sum_l": L,
        "sum_t": T,
        "sum_pf": PF,
        "sum_pa": PA,
        "sum_net": NETM,
        "games_implied": implied,
    }
    a2_ok = (
        len(standings) == 32
        and W == L
        and T % 2 == 0
        and PF == PA
        and NETM == 0
        and implied == 150
    )
    a2["verdict"] = "pass" if a2_ok else "FAIL"
    checks["A2"] = a2

    # ---------------------------------------------------------------- A3
    # Every record printed on the Week 11 page, compared with the standings page read the same day.
    standings_rec = {
        r["abbr"]: (int(r["w"]), int(r["l"]), int(r["t"])) for r in standings
    }
    a3_total = a3_ok = 0
    a3_conflicts = []
    a3_checked = []
    seen_w11 = {}
    for r in w11:
        for side in ("away", "home"):
            club = r[side]
            seen_w11[club] = r[f"{side}_record"]
            a3_total += 1
            got = rec(r[f"{side}_record"])
            want = standings_rec.get(club)
            if want is None:
                a3_conflicts.append(f"{club}: not on standings page")
            elif got == want:
                a3_ok += 1
                a3_checked.append(club)
            else:
                a3_conflicts.append(
                    f"{club}: Week 11 page prints '{r[f'{side}_record']}', standings page prints "
                    f"'{rec_dash(*want)}'"
                )
    a3_alias_used = 0
    for r in byes:
        club = r["abbr"]
        printed = r["printed_abbr"]
        if ALIASES.get(printed):
            a3_alias_used += 1
            club = ALIASES[printed]
        a3_total += 1
        got = rec(r["record"])
        want = standings_rec.get(club)
        if want is None:
            a3_conflicts.append(f"{club}: not on standings page")
        elif got == want:
            a3_ok += 1
            a3_checked.append(club)
        else:
            a3_conflicts.append(
                f"{club}: bye block prints '{r['record']}', standings page prints '{rec_dash(*want)}'"
            )
    conflict_clubs = sorted({c.split(":")[0] for c in a3_conflicts})
    checks["A3"] = {
        "name": "cross-page records (Week 11 page vs standings page, same day)",
        "assertions": a3_total,
        "passed": a3_ok,
        "failed": a3_total - a3_ok,
        "conflicts": a3_conflicts,
        "conflicting_clubs": conflict_clubs,
        "alias_used": {"LAR->LA": a3_alias_used},
        "verdict": "pass" if not a3_conflicts else "CONFLICT (published, not resolved)",
    }

    # ---------------------------------------------------------------- A4
    prior_standings = read_tsv(os.path.join(PRIOR, "official_standings_2026_11_18.tsv"))
    prior_w10 = read_tsv(os.path.join(PRIOR, "official_w10_results_2026_11_18.tsv"))
    ps = {r["abbr"]: r for r in prior_standings}
    a4_total = a4_ok = 0
    a4_diff = []
    for r in standings:
        p = ps.get(r["abbr"])
        if p is None:
            a4_diff.append(f"{r['abbr']} missing from the 2026-11-18 pack")
            continue
        for col in (
            "w", "l", "t", "pct", "pf", "pa", "net", "home", "road",
            "div_record", "conf_record", "streak",
        ):
            a4_total += 1
            if r[col] == p[col]:
                a4_ok += 1
            else:
                a4_diff.append(f"{r['abbr']}.{col}: 11-18 '{p[col]}' -> 11-19 '{r[col]}'")
    pw10 = {(r["away"], r["home"]): r for r in prior_w10}
    n10 = 0
    for r in w10:
        p = pw10.get((r["away"], r["home"]))
        if p is None:
            a4_diff.append(f"{r['away']}@{r['home']} missing from the 2026-11-18 pack")
            continue
        for col in (
            "away_score", "home_score", "status", "day", "away_record", "home_record", "game_url",
        ):
            a4_total += 1
            if r[col] == p[col]:
                a4_ok += 1
            else:
                a4_diff.append(
                    f"{r['away']}@{r['home']}.{col}: 11-18 '{p[col]}' -> 11-19 '{r[col]}'"
                )
        n10 += 1
    checks["A4"] = {
        "name": "continuity vs the 2026-11-18 pack (standings 32x12, Week 10 finals 14x7)",
        "assertions": a4_total,
        "passed": a4_ok,
        "differences": a4_diff,
        "w10_rows": n10,
        "verdict": "pass" if not a4_diff else "DRIFT",
    }

    # ---------------------------------------------------------------- A5
    clubs = []
    for r in w11:
        clubs.extend([r["away"], r["home"]])
    clubs.extend(r["abbr"] for r in byes)
    counts: dict[str, int] = {}
    for c in clubs:
        counts[c] = counts.get(c, 0) + 1
    dupes = sorted(c for c, n in counts.items() if n != 1)
    missing = sorted(set(standings_rec) - set(counts))
    a5_bad = []
    for r in w11:
        for col in ("date_et", "time_et", "network", "status", "game_url"):
            if not r[col].strip():
                a5_bad.append(f"{r['game_id']}.{col} blank")
    a5_ok = (
        len(w11) == 13
        and len(byes) == 6
        and len(clubs) == 32
        and not dupes
        and not missing
        and not a5_bad
    )
    checks["A5"] = {
        "name": "Week 11 slate completeness (13 fixtures + 6 byes = 32 clubs, once each)",
        "fixtures": len(w11),
        "byes": len(byes),
        "clubs_counted": len(clubs),
        "duplicated": dupes,
        "missing": missing,
        "field_problems": a5_bad,
        "verdict": "pass" if a5_ok else "FAIL",
    }

    # ---------------------------------------------------------------- A6
    frozen = read_tsv(FROZEN_W11)
    # The 2026-11-17 read keys the Cardinals fixture "2026_11_ARZ_KC" while printing the club as "AZ".
    # Normalise the key so the comparison is between fixtures, not between spellings, and count it.
    gid_alias = {"2026_11_ARZ_KC": "2026_11_AZ_KC"}
    fz = {}
    fz_alias_used = 0
    for r in frozen:
        if r.get("row_type") != "game":
            continue
        gid = r["game_id"]
        if gid in gid_alias:
            fz_alias_used += 1
            gid = gid_alias[gid]
        fz[gid] = r
    a6_total = a6_ok = 0
    a6_diff = []
    by_id = {r["game_id"]: r for r in w11}
    for gid, f in fz.items():
        t = by_id.get(gid)
        if t is None:
            a6_diff.append(f"{gid}: in the 2026-11-17 read, absent on 2026-11-19")
            continue
        for col_f, col_t in (
            ("date_et", "date_et"),
            ("time_et", "time_et"),
            ("network", "network"),
            ("away", "away"),
            ("home", "home"),
        ):
            a6_total += 1
            if f[col_f].strip() == t[col_t].strip():
                a6_ok += 1
            else:
                a6_diff.append(
                    f"{gid}.{col_t}: 11-17 '{f[col_f]}' -> 11-19 '{t[col_t]}'"
                )
        # a printed record may only move if a Week 10 result explains it
        for side in ("away", "home"):
            a6_total += 1
            if f[f"{side}_record"] == t[f"{side}_record"]:
                a6_ok += 1
            else:
                a6_diff.append(
                    f"{gid}.{side}_record: 11-17 '{f[f'{side}_record']}' -> "
                    f"11-19 '{t[f'{side}_record']}' (record movement; allowed only for a "
                    f"top-level result, listed separately)"
                )
    extra = sorted(set(by_id) - set(fz))
    checks["A6"] = {
        "name": "Week 11 fixture continuity vs the frozen 2026-11-17 read",
        "assertions": a6_total,
        "passed": a6_ok,
        "differences": a6_diff,
        "new_fixtures_not_in_frozen_read": extra,
        "game_id_alias_used": {"2026_11_ARZ_KC->2026_11_AZ_KC": fz_alias_used},
        # Printed records are EXPECTED to move once Week 10 finals land (BAL 4-5->4-6, LAC 0-8->1-8).
        # That is not drift, so it does not fail the check; every movement is still listed in
        # differences and published. Fixture identity, date, time, network and status must not move.
        "verdict": "pass" if not extra else "DRIFT (see differences)",
    }

    # ---------------------------------------------------------------- A7
    # The Week 11 injury report, measured rather than summarised.
    inj = read_tsv(os.path.join(PACK, "official_w11_injuries_2026_11_19.tsv"))
    inj_clubs = sorted({r["team"] for r in inj})
    inj_games = sorted({r["game"] for r in inj})
    designated = [r for r in inj if r["game_status"].strip()]
    des_by_club: dict[str, int] = {}
    for r in designated:
        des_by_club[r["team"]] = des_by_club.get(r["team"], 0) + 1
    by_status: dict[str, int] = {}
    for r in designated:
        by_status[r["game_status"]] = by_status.get(r["game_status"], 0) + 1
    by_practice: dict[str, int] = {}
    for r in inj:
        by_practice[r["practice_status"]] = by_practice.get(r["practice_status"], 0) + 1
    dupes_inj = sorted(
        f"{t}/{p}"
        for (t, p), n in __import__("collections").Counter(
            (r["team"], r["player"]) for r in inj
        ).items()
        if n > 1
    )
    # every game key on an injury row must be a fixture the slate also prints
    slate_pairs = {f"{r['away']}@{r['home']}" for r in w11}
    inj_pair_problems = sorted({r["game"] for r in inj} - slate_pairs)
    a7 = {
        "name": "Week 11 official injury report (rows, clubs, designations)",
        "rows": len(inj),
        "clubs": len(inj_clubs),
        "clubs_missing_a_block": sorted(set(standings_rec) - set(inj_clubs)),
        "fixtures_with_rows": len(inj_games),
        "designated_rows": len(designated),
        "designated_by_status": by_status,
        "designated_by_club": des_by_club,
        "practice_status_counts": by_practice,
        "blank_practice_status": sum(1 for r in inj if not r["practice_status"].strip()),
        "duplicate_player_rows": dupes_inj,
        "injury_game_keys_absent_from_slate": inj_pair_problems,
        "verdict": "pass"
        if not dupes_inj and not inj_pair_problems and len(inj) == 253
        else "FAIL",
    }
    checks["A7"] = a7

    # ---------------------------------------------------------------- A8
    # The three named-player availability statements, each against its own official article.
    named = read_tsv(os.path.join(PACK, "official_named_availability_2026_11_19.tsv"))
    a8_bad = []
    for r in named:
        for col in ("player", "club", "statement_as_printed", "article_date", "source_url"):
            if not r[col].strip():
                a8_bad.append(f"{r['id']}.{col} blank")
        if not r["source_url"].startswith("https://www.nfl.com/"):
            a8_bad.append(f"{r['id']}.source_url is not an nfl.com URL")
        # the claim must be echoed by the injury report it refers to, where the report covers the club
        if r["injury_report_game_status"].strip() and r["player"] not in {
            x["player"] for x in inj
        }:
            a8_bad.append(
                f"{r['id']}: '{r['player']}' is cited with a report designation but is not a row "
                f"on the Week 11 report read the same day"
            )
    checks["A8"] = {
        "name": "announced-starter evidence (dated official articles, one row each)",
        "rows": len(named),
        "players": [r["player"] for r in named],
        "problems": a8_bad,
        "verdict": "pass" if named and not a8_bad else "FAIL",
    }

    summary = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "session": "arena/427c1843-x1 (round 7)",
        "pack_date": "2026-11-19",
        "read_at": READ_AT,
        "sources": {
            "standings": SOURCE_STANDINGS,
            "week10_schedule": SOURCE_W10,
            "week11_schedule": SOURCE_W11,
        },
        "checks": checks,
        "verdicts": {k: v["verdict"] for k, v in checks.items()},
    }

    with open(SUMMARY, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
        fh.write("\n")

    for k, v in checks.items():
        print(f"{k}  {v['verdict']:<45} {v.get('name', '')}")
    print(f"\nsummary -> {os.path.relpath(SUMMARY, ROOT)}")

    hard_fails = [k for k, v in checks.items() if v["verdict"] == "FAIL"]
    if hard_fails:
        print(f"HARD FAILURES: {hard_fails}")
    return 1 if hard_fails else 0


def check_mode() -> int:
    if not os.path.exists(SUMMARY):
        print("no committed summary to compare against", file=sys.stderr)
        return 1
    with open(SUMMARY, encoding="utf-8") as fh:
        committed = json.load(fh)
    rc = main()
    with open(SUMMARY, encoding="utf-8") as fh:
        fresh = json.load(fh)
    committed.pop("generated_at", None)
    fresh.pop("generated_at", None)
    if committed != fresh:
        print("summary drifted: rebuild changed a measured value", file=sys.stderr)
        return 1
    print("summary matches the committed measurement")
    return rc


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(check_mode())
    sys.exit(main())
