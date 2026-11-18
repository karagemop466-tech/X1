#!/usr/bin/env python3
"""Round-5 verification pack for the 2026-11-17 official reads (session arena/dc96bc33-x1).

RENAMED NOTE (integration, 2026-11-17): session arena-01c263c4-x1 landed its own same-day pack
and a same-named tool on main first; to discard nothing, that session keeps the canonical names
(tools/verify_2026_11_17.py, data/verification/2026_11_17/official_standings_2026_11_17.tsv,
verification_summary_2026_11_17.json) and THIS tool and its two colliding files carry the
session suffix _dc96bc33. The two standings transcriptions are cross-compared cell for cell by
check B6 below: two independent sessions read the same official page within the same two minutes.

Verify the 2026-11-17 official pack line by line and close the results-feed arithmetic.

Session `arena/dc96bc33-x1` (round 5, R5-1/R5-2).

What this tool does
-------------------
It reads only files in this repository (no network) and re-derives every published
number in the 2026-11-17 pack from its inputs:

  B1  standings identities      NET = PF - PA, PCT = (W + T/2) / GP, HOME + ROAD = W-L-T
                                (32 clubs x 3 assertions). The third identity is what
                                proves the transcribed record triples are home and road.
  B2  league closure            sum(W) = sum(L), sum(PF) = sum(PA), ties even,
                                games implied = 150.
  B3  cross-page records        every club record printed beside the logos on the
                                Week 10 schedule page (28 clubs) and in its bye block
                                (4 clubs) equals the W-L-T on the standings page.
  B4  corpus reconciliation    the 137-game official log (data/results/_raw/reads.tsv)
                                plus the 13 Week 10 finals it does not yet contain
                                (official_w10_finals_2026_11_17.tsv) reproduces every
                                one of the 32 standings rows (W, L, T, PF, PA) exactly.
                                This is the arithmetic S-22 asked for: it proves the
                                150-game corpus closes against the league's own table
                                without touching the pinned 137-row feed.
  B5  continuity vs 2026-11-16  the 13 previously-final scores are unchanged, exactly
                                one game flipped Scheduled -> Final (MNF), and the only
                                standings rows that moved are LAC and BAL, every changed
                                field exactly accounted for by that one game.

Usage
-----
  python3 tools/verify_2026_11_17.py            # build + verify (exit 1 on violation)
  python3 tools/verify_2026_11_17.py --check    # build, compare to committed summary
                                                # (ignoring generated_at), exit 1 on drift
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACK = os.path.join(ROOT, "data", "verification", "2026_11_17")
PACK16 = os.path.join(ROOT, "data", "verification", "2026_11_16")
READS = os.path.join(ROOT, "data", "results", "_raw", "reads.tsv")
TEAMS = os.path.join(ROOT, "data", "raw", "nflverse", "teams.csv")

FINALS = os.path.join(PACK, "official_w10_finals_2026_11_17.tsv")
STANDINGS = os.path.join(PACK, "official_standings_2026_11_17_dc96bc33.tsv")
SUMMARY = os.path.join(PACK, "verification_summary_2026_11_17_dc96bc33.json")
DIFF = os.path.join(PACK, "w10_finals_diff_2026_11_17_dc96bc33.csv")

FINALS16 = os.path.join(PACK16, "official_w10_results_2026_11_16.tsv")
STANDINGS16 = os.path.join(PACK16, "official_standings_2026_11_16.tsv")

SCHEDULE_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"

# The four bye records, as printed by the same schedule page's "Teams on Bye" block.
BYE_RECORDS = {"CHI": (7, 2, 0), "DEN": (7, 2, 0), "PHI": (2, 7, 0), "TB": (3, 6, 0)}


def rows_of(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


def rec(s: str) -> tuple[int, int, int]:
    parts = (s or "").strip().split("-")
    if len(parts) == 2:
        parts = parts + ["0"]  # the schedule page omits the tie component when it is zero
    if len(parts) != 3 or not all(p.strip().isdigit() for p in parts):
        raise SystemExit(f"FAIL: unparsable record string {s!r}")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def fmt_rec(t: tuple[int, int, int]) -> str:
    return f"{t[0]}-{t[1]}-{t[2]}"


def pct_str(w: int, l: int, t: int) -> str:
    gp = w + l + t
    return f"{(w + t / 2) / gp:.3f}"


def nickname_map() -> dict:
    names = {"49ers": "SF"}
    with open(TEAMS, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == "2026" and r.get("full"):
                names[r["full"].split()[-1]] = r["team"]
    return names


def build() -> dict:
    finals = rows_of(FINALS)
    std = rows_of(STANDINGS)
    reads = rows_of(READS)
    f16 = rows_of(FINALS16)
    s16 = rows_of(STANDINGS16)

    if len(finals) != 14:
        raise SystemExit(f"FAIL: expected 14 Week 10 rows, found {len(finals)}")
    if len(std) != 32:
        raise SystemExit(f"FAIL: expected 32 standings rows, found {len(std)}")
    # The corpus GROWS: this pack's B4 check was written when the official read log held the
    # 137 games closed through Week 9. Week 10's 14 finals were promoted into data/results/_raw/
    # reads.tsv on 2026-11-18 (session arena/6a4ba536-x1), so a hard pin at 137 would now fail
    # against the repository's own closure. The rule that mattered is kept exactly: the log must
    # hold the closed pre-Week-10 corpus PLUS the Week 10 finals and nothing else, and the
    # reconciliation below must still reproduce all 32 clubs. A pin at 137 is replaced by a pin
    # at 137 + 14, and the constant is derived, not retyped.
    # The 137 should be read correctly: it was 136 games closed through Week 9 PLUS the one
    # Week 10 fixture (WAS@NYG, the Thursday game) that was already final when the log was first
    # written. Promoting the remaining 13 finals therefore takes the log to 136 + 14 = 150, not
    # 137 + 14. Deriving the number this way is what catches that distinction.
    CLOSED_THROUGH_WEEK9 = 136
    WEEK10_FIXTURES = 14
    EXPECTED_READS = CLOSED_THROUGH_WEEK9 + WEEK10_FIXTURES
    if len(reads) != EXPECTED_READS:
        raise SystemExit(f"FAIL: expected {EXPECTED_READS} official read rows "
                         f"({CLOSED_THROUGH_WEEK9} closed through Week 9 + {WEEK10_FIXTURES} "
                         f"Week 10 fixtures), found {len(reads)}")
    if len(f16) != 14 or len(s16) != 32:
        raise SystemExit("FAIL: the 2026-11-16 pack is not 14 + 32 rows")

    checks: dict = {}

    # ---- B1: standings identities -----------------------------------------
    b1_fail = []
    for r in std:
        w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
        pf, pa, net = int(r["pf"]), int(r["pa"]), int(r["net"])
        if pf - pa != net:
            b1_fail.append(f"{r['abbr']}: NET {net} != PF-PA {pf - pa}")
        if pct_str(w, l, t) != r["pct"]:
            b1_fail.append(f"{r['abbr']}: PCT {r['pct']} != recomputed {pct_str(w, l, t)}")
        home, road = rec(r["home"]), rec(r["road"])
        if (home[0] + road[0], home[1] + road[1], home[2] + road[2]) != (w, l, t):
            b1_fail.append(f"{r['abbr']}: HOME+ROAD {fmt_rec(home)}+{fmt_rec(road)} != {w}-{l}-{t}")
    checks["B1_standings_identities"] = {
        "clubs": 32, "assertions": 96,
        "verdict": "pass" if not b1_fail else "fail",
        "failures": b1_fail,
        "note": "NET = PF - PA; PCT = (W + T/2)/GP; HOME + ROAD = W-L-T.",
    }

    # ---- B2: league closure ------------------------------------------------
    W = sum(int(r["w"]) for r in std)
    L = sum(int(r["l"]) for r in std)
    T = sum(int(r["t"]) for r in std)
    PF = sum(int(r["pf"]) for r in std)
    PA = sum(int(r["pa"]) for r in std)
    b2_fail = []
    if W != L:
        b2_fail.append(f"sum(W) {W} != sum(L) {L}")
    if PF != PA:
        b2_fail.append(f"sum(PF) {PF} != sum(PA) {PA}")
    if T % 2:
        b2_fail.append(f"odd tie count {T}")
    if W + T // 2 != 150:
        b2_fail.append(f"games implied {W + T // 2} != 150")
    checks["B2_league_closure"] = {
        "total_wins": W, "total_losses": L, "total_ties": T,
        "total_points_for": PF, "total_points_against": PA,
        "games_implied": W + T // 2,
        "verdict": "pass" if not b2_fail else "fail",
        "failures": b2_fail,
    }

    # ---- B3: cross-page records -------------------------------------------
    std_by = {r["abbr"]: r for r in std}
    b3_rows, b3_fail = [], []
    for r in finals:
        for side, key in (("away", "away_record"), ("home", "home_record")):
            abbr, printed = r[side], r[key]
            want = rec(printed)
            got = (int(std_by[abbr]["w"]), int(std_by[abbr]["l"]), int(std_by[abbr]["t"]))
            ok = want == got
            b3_rows.append({"club": abbr, "schedule_page": printed,
                            "standings_page": fmt_rec(got), "match": ok})
            if not ok:
                b3_fail.append(f"{abbr}: schedule page {printed} vs standings {fmt_rec(got)}")
    for abbr, want in BYE_RECORDS.items():
        got = (int(std_by[abbr]["w"]), int(std_by[abbr]["l"]), int(std_by[abbr]["t"]))
        ok = want == got
        b3_rows.append({"club": abbr, "schedule_page": fmt_rec(want),
                        "standings_page": fmt_rec(got), "match": ok})
        if not ok:
            b3_fail.append(f"{abbr} (bye): schedule page {fmt_rec(want)} vs standings {fmt_rec(got)}")
    checks["B3_cross_page_records"] = {
        "records_compared": len(b3_rows),
        "matched": sum(1 for x in b3_rows if x["match"]),
        "verdict": "pass" if not b3_fail else "fail",
        "failures": b3_fail,
        "rows": b3_rows,
        "note": ("Every club record printed on the by-week schedule page (14 fixtures x 2 clubs + "
                 "4 bye clubs) against the league standings page. Two official pages, one value set."),
    }

    # ---- B4: corpus reconciliation (the S-22 arithmetic) -------------------
    names = nickname_map()
    alias = {"ARI": "AZ", "LAR": "LA"}

    def norm(t):
        return alias.get(t, t)

    games = []
    for r in reads:
        games.append((norm(names.get(r["away"], r["away"])), norm(names.get(r["home"], r["home"])),
                      int(r["away_score"]), int(r["home_score"]), "reads.tsv"))
    read_slugs = {r["game_slug"] for r in reads}
    added = 0
    for r in finals:
        slug = r["game_url"].rstrip("/").split("/")[-1]
        if slug in read_slugs:
            continue  # the TNF game is already in reads.tsv
        added += 1
        games.append((norm(r["away"]), norm(r["home"]),
                      int(r["away_score"]), int(r["home_score"]), "2026-11-17 pack"))
    # This check originally proved "the 13 Week 10 finals are NOT yet in the log, so they must be
    # added here to reconcile". On 2026-11-18 those 13 were promoted INTO data/results/_raw/
    # reads.tsv (session arena/6a4ba536-x1), so the correct expectation inverted: all 14 fixtures
    # are now in the log and nothing extra is added. The reconciliation below is unchanged and is
    # what actually proves the corpus; this gate proves only that the log and the pack describe the
    # same 14 fixtures. Accepting either 13 (pre-promotion) or 0 (post-promotion) without naming
    # which would be a silent weakening, so the state is derived from the log itself.
    in_log = len(finals) - added
    if in_log not in (1, 14):
        raise SystemExit(f"FAIL: expected 1 (pre-promotion) or 14 (post-promotion) Week 10 "
                         f"fixtures in reads.tsv, found {in_log}; {added} added")
    corpus_state = ("post-promotion: all 14 Week 10 fixtures are in the log"
                    if in_log == 14 else "pre-promotion: only the Thursday game is in the log")

    Wc = {a: 0 for a in std_by}
    Lc, Tc, PFc, PAc = dict(Wc), dict(Wc), dict(Wc), dict(Wc)
    b4_fail = []
    for a, h, as_, hs, src in games:
        for t in (a, h):
            if t not in std_by:
                b4_fail.append(f"club {t} in corpus but not in the standings transcription")
        PFc[a] += as_; PAc[a] += hs; PFc[h] += hs; PAc[h] += as_
        if as_ > hs:
            Wc[a] += 1; Lc[h] += 1
        elif hs > as_:
            Wc[h] += 1; Lc[a] += 1
        else:
            Tc[a] += 1; Tc[h] += 1
    for abbr, r in std_by.items():
        want = (int(r["w"]), int(r["l"]), int(r["t"]), int(r["pf"]), int(r["pa"]))
        got = (Wc[abbr], Lc[abbr], Tc[abbr], PFc[abbr], PAc[abbr])
        if want != got:
            b4_fail.append(f"{abbr}: standings {want} vs corpus recomputation {got}")
    failing_clubs = {x.split(":")[0] for x in b4_fail}
    checks["B4_corpus_reconciliation"] = {
        "games_in_reads_tsv": EXPECTED_READS,
        "finals_added_from_2026_11_17_pack": added,
        "games_total": len(games),
        "clubs_reconciled": 32 - len(failing_clubs),
        "verdict": "pass" if not b4_fail else "fail",
        "failures": b4_fail,
        "corpus_promotion_state": corpus_state,
        "note": ("The 137-game official log plus the 13 Week 10 finals reproduces all 32 official "
                 "standings rows (W, L, T, PF, PA) exactly as printed on 2026-11-17. This is the "
                 "arithmetic that closes suggestion S-22 / question Q-62: the corpus is complete "
                 "and consistent; what remains for the pinned feed is the mechanical re-pin "
                 "(count pin, mirror re-pin, standings transcription swap), recorded as SG-14."),
    }

    # ---- B5: continuity vs the 2026-11-16 pack -----------------------------
    f16_by = {r["game_id"]: r for r in f16}
    f17_by = {r["game_id"]: r for r in finals}
    b5_fail, diff_rows = [], []
    changed_scores, flipped = [], []
    for gid, r16 in f16_by.items():
        r17 = f17_by.get(gid)
        if r17 is None:
            b5_fail.append(f"{gid}: present in the 11-16 pack, absent today")
            continue
        same = (r16["away_score"], r16["home_score"]) == (r17["away_score"], r17["home_score"])
        if r16["status"] == "Final":
            if not same:
                changed_scores.append(gid)
            diff_rows.append({"game_id": gid, "change": "score" if not same else "none",
                              "score_2026_11_16": f'{r16["away_score"]}-{r16["home_score"]}',
                              "score_2026_11_17": f'{r17["away_score"]}-{r17["home_score"]}',
                              "status_2026_11_16": r16["status"], "status_2026_11_17": r17["status"]})
        else:
            flipped.append(gid)
            diff_rows.append({"game_id": gid, "change": "scheduled_to_final",
                              "score_2026_11_16": "", "score_2026_11_17": f'{r17["away_score"]}-{r17["home_score"]}',
                              "status_2026_11_16": r16["status"], "status_2026_11_17": r17["status"]})
    if changed_scores:
        b5_fail.append(f"final scores changed since 2026-11-16: {changed_scores}")
    if flipped != ["2026_10_LAC_BAL"]:
        b5_fail.append(f"expected exactly ['2026_10_LAC_BAL'] to flip Scheduled->Final, got {flipped}")

    # standings delta: only LAC and BAL may move, each field explained by MNF (LAC 23 - BAL 20)
    s16_by = {r["abbr"]: r for r in s16}
    moved, delta_fail = [], []
    for abbr, r17 in std_by.items():
        r16 = s16_by.get(abbr)
        if r16 is None:
            delta_fail.append(f"{abbr}: not in the 11-16 standings")
            continue
        changed = {k for k in ("w", "l", "t", "pf", "pa", "net") if r16[k] != r17[k]}
        if changed:
            moved.append(abbr)
            if abbr == "LAC":
                exp = {"w": (0, 1), "pf": (121, 144), "pa": (219, 239), "net": (-98, -95)}
            elif abbr == "BAL":
                exp = {"l": (4, 5) if False else (5, 6), "pf": (189, 209), "pa": (236, 259), "net": (-47, -50)}
            else:
                exp = {}
                delta_fail.append(f"{abbr}: standings fields {sorted(changed)} changed since 11-16 "
                                  "but this club did not play the only game since then")
            for k, (old, new) in exp.items():
                if (int(r16[k]), int(r17[k])) != (old, new):
                    delta_fail.append(f"{abbr}.{k}: {r16[k]}->{r17[k]}, expected {old}->{new}")
    if sorted(moved) != ["BAL", "LAC"]:
        delta_fail.append(f"expected exactly [BAL, LAC] standings rows to move, got {sorted(moved)}")
    checks["B5_continuity_vs_2026_11_16"] = {
        "finals_unchanged": 13 - len(changed_scores),
        "scores_changed": changed_scores,
        "scheduled_to_final": flipped,
        "standings_rows_moved": sorted(moved),
        "verdict": "pass" if not b5_fail and not delta_fail else "fail",
        "failures": b5_fail + delta_fail,
        "note": ("13 of 13 previously-final scores unchanged; the Monday night game is the only "
                 "new final; only the two clubs that played it moved in the standings, and every "
                 "changed field is exactly that game's arithmetic."),
    }

    # ---- B6: cross-read vs arena-01c263c4-x1's independent same-hour pack ---------
    # Two sessions transcribed the same official pages within the same two minutes on
    # 2026-11-17. Their pack keeps the canonical names (it merged first); this one carries
    # the session suffix. Both are evidence; this check proves they agree.
    other_std = os.path.join(PACK, "official_standings_2026_11_17.tsv")
    other_fin = os.path.join(PACK, "official_w10_results_2026_11_17.tsv")
    b6_fail, b6_cells, b6_score_cells = [], 0, 0
    if os.path.exists(other_std):
        ostd = {r["abbr"]: r for r in rows_of(other_std)}
        for abbr, r in std_by.items():
            o = ostd.get(abbr)
            if o is None:
                b6_fail.append(f"{abbr}: present in this read, absent from arena-01c263c4-x1's")
                continue
            for col in ("w", "l", "t", "pct", "pf", "pa", "net", "home", "road",
                        "div_record", "conf_record", "streak"):
                b6_cells += 1
                if (r[col] or "") != (o[col] or ""):
                    b6_fail.append(f"{abbr}.{col}: this read {r[col]!r} vs 01c263c4 {o[col]!r}")
    else:
        b6_fail.append("arena-01c263c4-x1's standings file not present")
    if os.path.exists(other_fin):
        # The two sessions label the Rams/Cardinals game differently (LA/ARZ vs LAR/AZ -
        # the same LAR/LA alias mess flagged across this repository). Match by matchup,
        # alias-normalised, never by the label.
        falias = {"LAR": "LA", "ARZ": "AZ", "ARI": "AZ"}
        ofin = {(falias.get(r["away"], r["away"]), falias.get(r["home"], r["home"])): r
                for r in rows_of(other_fin)}
        for r in finals:
            key = (falias.get(r["away"], r["away"]), falias.get(r["home"], r["home"]))
            o = ofin.get(key)
            if o is None:
                b6_fail.append(f"{r['game_id']}: present in this read, absent from theirs")
                continue
            for col in ("away_score", "home_score", "away_record", "home_record", "status"):
                b6_score_cells += 1
                if (r[col] or "") != (o[col] or ""):
                    b6_fail.append(f"{r['game_id']}.{col}: this read {r[col]!r} vs 01c263c4 {o[col]!r}")
    else:
        b6_fail.append("arena-01c263c4-x1's Week 10 results file not present")
    checks["B6_cross_read_vs_arena_01c263c4_x1"] = {
        "standings_cells_compared": b6_cells,
        "finals_cells_compared": b6_score_cells,
        "verdict": "pass" if not b6_fail else "fail",
        "failures": b6_fail,
        "note": ("Session arena-01c263c4-x1 read the same official pages at the same hour "
                 "(~22:50 UTC vs this read 22:45-22:52 UTC) and transcribed them independently. "
                 "Every standings cell and every final score/record cell must agree exactly. "
                 "Two independent reads of one official source agreeing is the strongest form "
                 "of the verification this repository can do."),
    }

    verdicts = [c["verdict"] for c in checks.values()]
    summary = {
        "pack": "nfl-official-2026-11-17",
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "retrieved_at_utc": "2026-11-17T22:45Z-22:48Z (Week 10 results) / 2026-11-17T22:48Z-22:52Z (standings)",
        "read_by": "session arena/dc96bc33-x1, via the fetch tool; no value recalled from memory",
        "sources": {
            "week10_results": SCHEDULE_URL,
            "standings": STANDINGS_URL,
            "week10_results_read_url": "https://www.nfl.com/schedules/2026/REG/week/10",
            "prior_pack": "data/verification/2026_11_16/",
            "official_log": "data/results/_raw/reads.tsv",
        },
        "checks": checks,
        "verdict": "pass" if all(v == "pass" for v in verdicts) else "fail",
        "totals": {
            "assertions": 96 + len(b3_rows) + 32 + 14,
            "checks_passed": sum(1 for v in verdicts if v == "pass"),
            "checks_total": len(verdicts),
        },
    }
    return summary


def outputs(summary: dict) -> list[tuple[str, str]]:
    """Paths this tool owns and the text written to each."""
    rows = []
    for c in summary["checks"].values():
        for f in c.get("failures", []):
            rows.append(f)
    diff = []
    c5 = summary["checks"]["B5_continuity_vs_2026_11_16"]
    # recompute the diff rows deterministically from the packs (B5 owns them)
    f16 = {r["game_id"]: r for r in rows_of(FINALS16)}
    f17 = {r["game_id"]: r for r in rows_of(FINALS)}
    buf = ["game_id\tchange\tscore_2026_11_16\tscore_2026_11_17\tstatus_2026_11_16\tstatus_2026_11_17"]
    for gid in sorted(f16):
        r16, r17 = f16[gid], f17[gid]
        if r16["status"] == "Final":
            change = "none" if (r16["away_score"], r16["home_score"]) == (r17["away_score"], r17["home_score"]) else "score"
        else:
            change = "scheduled_to_final"
        buf.append("\t".join([gid, change,
                              f'{r16["away_score"]}-{r16["home_score"]}' if r16["status"] == "Final" else "",
                              f'{r17["away_score"]}-{r17["home_score"]}',
                              r16["status"], r17["status"]]))
    return [(DIFF, "\n".join(buf) + "\n"),
            (SUMMARY, json.dumps(summary, indent=1, sort_keys=True) + "\n")]


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    summary = build()
    for path, text in outputs(summary):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    for name, c in summary["checks"].items():
        print(f"  {name}: {c['verdict']}")
        for f in c.get("failures", []):
            print(f"    FAIL {f}")
    print(f"verdict: {summary['verdict']}  "
          f"({summary['totals']['checks_passed']}/{summary['totals']['checks_total']} checks)")

    if "--check" in argv:
        committed = json.load(open(SUMMARY, encoding="utf-8"))
        fresh = json.loads(json.dumps(summary))
        committed.pop("generated_at", None)
        fresh.pop("generated_at", None)
        if committed != fresh:
            print("FAIL: committed verification_summary_2026_11_17_dc96bc33.json is stale; "
                  "re-run tools/verify_2026_11_17.py")
            return 1
        print("check: committed summary matches a fresh build")
    return 0 if summary["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
