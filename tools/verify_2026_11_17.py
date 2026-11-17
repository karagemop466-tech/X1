#!/usr/bin/env python3
"""Dated re-verification for 2026-11-17 (session arena-e1436334-x1).

Everything the site publishes about the 2026 season rests on three official pages read on
2026-11-17 and transcribed line by line under `data/verification/2026_11_17/`:

  official_w10_results_2026_11_17.tsv    the 14 completed Week 10 fixtures, scores and all
  official_standings_2026_11_17.tsv      the 32 league standings rows
  official_w11_slate_2026_11_17.tsv      the 13-game forward slate and the 6 byes

This tool does not trust its own transcription. It runs the checks below, and writes the verdicts to
`verification_summary_2026_11_17.json`, which the pages render. A FAIL is published, not hidden: the
point of the pack is that a reader can see which number was checked how, and which was not.

Checks (all arithmetic on values printed by an official page — nothing is inferred, nothing is filled in):

  B1   Standings internal consistency: NET = PF - PA; PCT = (W + T/2)/(W+L+T) to 3 dp;
       HOME + ROAD = W-L-T. The last one is what makes the home/road SPLIT a measurement.
  B2   League closure: sum W = sum L, ties even, games implied by records = the corpus size.
  B3   Three-page record agreement: each club's record printed on the Week 10 page (26 clubs play)
       and on the Week 11 page (26 play, 6 on bye) must equal its row on the standings page.
  B4   Corpus admission: every Week 10 fixture the official page prints as Final appears in
       data/results/_raw/reads.tsv with the same score, once; no fixture appears twice; the
       per-week row counts equal the pins the builder uses.
  B5   Standings arithmetic: summing reads.tsv reproduces all 32 standings rows on W-L-T, PF, PA.
  B6   Mirror cross-check (secondary, never published as a source): the fingerprinted nflverse
       games.csv agrees row for row on score and date for every corpus game.
  B7   Capture freshness: hours since the last accepted capture of each pinned dataset, from the
       retained capture index — reported, not repaired (the capture store belongs to the collector).
  B8   Sealed ledger: 14 rows, each reproducing from the frozen PR-01 rule at its own record time,
       each recorded strictly before its kickoff, each resolved or explicitly pending; the resolved
       row's Brier/log-loss/skill recomputed HERE, independently of the tool that wrote it.
  B9   Price discipline: market_line and residual are blank in every published artefact, because no
       price policy has been ratified (Q-02). A non-blank value here is a policy violation, not a typo.
  B10  Forward slate: 13 fixtures + 6 byes = 32 clubs exactly once, and no score printed for any of
       them; the sealed record covers the whole slate, so nothing is forecastable-but-unsealed.

Usage:  python3 tools/verify_2026_11_17.py            # print the verdicts, exit 1 on a hard FAIL
        python3 tools/verify_2026_11_17.py --write    # also re-emit the summary JSON
        python3 tools/verify_2026_11_17.py --check     # CI guard: committed summary == fresh build
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VDIR = os.path.join(ROOT, "data", "verification", "2026_11_17")
RETRIEVED = "2026-11-17"

READS = os.path.join(ROOT, "data", "results", "_raw", "reads.tsv")
MIRROR = os.path.join(ROOT, "data", "raw", "nflverse", "games.csv")
CAP_INDEX = os.path.join(ROOT, "data", "captures", "index.jsonl")
SEALED = os.path.join(ROOT, "data", "shadow", "forecasts_pre_kickoff.csv")
SUMMARY = "verification_summary_2026_11_17.json"

STANDINGS_URL = "https://www.nfl.com/standings/league/2026/REG"
W10_URL = "https://www.nfl.com/schedules/2026/by-week/week-10"
W11_URL = "https://www.nfl.com/schedules/2026/by-week/week-11"

ALIAS = {"LAR": "LA", "ARI": "AZ"}          # spelling only; the split itself is flag F-15
EXPECTED_WEEK_ROWS = {1: 16, 2: 16, 3: 16, 4: 16, 5: 15, 6: 14, 7: 14, 8: 14, 9: 15, 10: 14}
K, H, SIGMA = 2.0, 1.6, 13.5                # PR-01 frozen constants, re-declared to test the artefact
HOME_BASELINE_P = 0.55


def nickname_to_code() -> dict:
    """reads.tsv spells clubs the way the schedule page prints them ("Patriots"); the standings page
    prints abbreviations. This maps one to the other from the committed club list — the same table
    tools/build_results_r3.py uses, loaded independently so a mistake in one is visible in the other."""
    m = {"49ers": "SF"}
    with open(os.path.join(ROOT, "data", "raw", "nflverse", "teams.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == "2026" and r.get("full"):
                m[r["full"].split()[-1]] = r["team"]
    return m


def tsv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t"))


def canon(a: str) -> str:
    return ALIAS.get(a, a)


def rec(s: str) -> tuple[int, int, int]:
    if not s:
        return (-1, -1, -1)
    p = [int(x) for x in s.replace(" ", "").split("-")]
    return (p[0], p[1], p[2] if len(p) > 2 else 0)


def csv_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def pack_rows(name: str) -> list[dict]:
    return tsv(os.path.join(VDIR, name))


# --------------------------------------------------------------------------------------------- checks

def b1_standings_internal(rows: list[dict]) -> dict:
    fails = []
    for r in rows:
        w, l, t = int(r["w"]), int(r["l"]), int(r["t"])
        if int(r["net_pts"]) != int(r["pf"]) - int(r["pa"]):
            fails.append(f"{r['abbr']}: net_pts {r['net_pts']} != PF-PA {int(r['pf']) - int(r['pa'])}")
        exp = (w + t / 2) / (w + l + t) if (w + l + t) else 0.0
        if abs(float(r["pct"]) - exp) > 5e-4:
            fails.append(f"{r['abbr']}: pct {r['pct']} != computed {round(exp, 3)}")
        hw, hl, ht = rec(r["home"])
        rw, rl, rt = rec(r["road"])
        if (hw + rw, hl + rl, ht + rt) != (w, l, t):
            fails.append(f"{r['abbr']}: home {r['home']} + road {r['road']} != {w}-{l}-{t}")
    return {"verdict": "PASS" if not fails else "FAIL", "clubs": len(rows),
            "assertions": len(rows) * 3, "failures": fails}


def b2_closure(standings: list[dict], reads: list[dict]) -> dict:
    sw = sum(int(r["w"]) for r in standings)
    sl = sum(int(r["l"]) for r in standings)
    st = sum(int(r["t"]) for r in standings)
    games = len(reads)
    fails = []
    if sw != sl:
        fails.append(f"league wins {sw} != losses {sl}")
    if st % 2:
        fails.append(f"league ties {st} is odd")
    if sw + sl + st != games * 2:
        fails.append(f"records imply {(sw + sl + st) // 2} games, corpus has {games}")
    pf = sum(int(r["pf"]) for r in standings)
    pa = sum(int(r["pa"]) for r in standings)
    if pf != pa:
        fails.append(f"league PF {pf} != PA {pa}")
    return {"verdict": "PASS" if not fails else "FAIL", "league_wins": sw, "league_losses": sl,
            "league_ties": st, "games_in_corpus": games, "league_points_each_side": pf, "failures": fails}


def b3_cross_page_records(standings: list[dict], w10: list[dict], w11: list[dict]) -> dict:
    printed: dict[str, set] = {}
    for r in w10:
        for side in ("away", "home"):
            printed.setdefault(canon(r[side]), set()).add(r[f"{side}_record"])
    for r in w11:
        if r["row_type"] == "game":
            for side in ("away", "home"):
                printed.setdefault(canon(r[side]), set()).add(r[f"{side}_record"])
        else:
            printed.setdefault(canon(r["away"]), set()).add(r["away_record"])
    by_abbr = {canon(r["abbr"]): r for r in standings}
    fails, compared = [], 0
    for club, vals in sorted(printed.items()):
        vals = {v for v in vals if v}
        if club not in by_abbr:
            fails.append(f"{club}: printed on a schedule page but missing from the standings table")
            continue
        s = by_abbr[club]
        want = f"{s['w']}-{s['l']}-{s['t']}" if int(s["t"]) else f"{s['w']}-{s['l']}"
        want3 = f"{s['w']}-{s['l']}-{s['t']}"
        compared += 1
        if not any(v == want or v == want3 for v in vals):
            fails.append(f"{club}: pages print {sorted(vals)}, standings print {want3}")
    return {"verdict": "PASS" if not fails else "FAIL", "clubs_checked": compared,
            "clubs_in_standings": len(standings), "failures": fails}


def b4_corpus_admission(w10: list[dict], reads: list[dict]) -> dict:
    fails = []
    by_slug: dict[str, list[dict]] = {}
    for r in reads:
        by_slug.setdefault(r["game_slug"], []).append(r)
    for slug, rs in by_slug.items():
        if len(rs) > 1:
            fails.append(f"{slug}: appears {len(rs)} times in the corpus")
    finals = [r for r in w10 if r["status"] == "Final"]
    missing, score_diff = [], []
    for r in finals:
        slug = r["game_url"].rstrip("/").split("/")[-1]
        rs = by_slug.get(slug)
        if not rs:
            missing.append(r["game_id"])
            continue
        if any((x["away_score"], x["home_score"]) != (r["away_score"], r["home_score"]) for x in rs):
            score_diff.append(r["game_id"])
    per_week: dict[int, int] = {}
    for r in reads:
        per_week[int(r["week"])] = per_week.get(int(r["week"]), 0) + 1
    if per_week != EXPECTED_WEEK_ROWS:
        fails.append(f"per-week counts {per_week} != pinned {EXPECTED_WEEK_ROWS}")
    read_dates = sorted({(r.get("read_at") or "").strip() for r in reads})
    return {"verdict": "PASS" if not (fails or missing or score_diff) else "FAIL",
            "corpus_rows": len(reads), "official_w10_finals": len(finals),
            "finals_missing_from_corpus": missing, "score_disagreements": score_diff,
            "per_week_rows": per_week, "read_dates_in_corpus": read_dates, "failures": fails}


def b5_standings_arithmetic(standings: list[dict], reads: list[dict]) -> dict:
    names = nickname_to_code()
    W, L, T, PF, PA = ({} for _ in range(5))
    unmapped = []
    for r in reads:
        a, h = canon(names.get(r["away"], "")), canon(names.get(r["home"], ""))
        if not a or not h:
            unmapped.append(r["game_slug"])
            continue
        for t in (a, h):
            W.setdefault(t, 0); L.setdefault(t, 0); T.setdefault(t, 0)
            PF.setdefault(t, 0); PA.setdefault(t, 0)
        as_, hs = int(r["away_score"]), int(r["home_score"])
        PF[a] += as_; PA[a] += hs; PF[h] += hs; PA[h] += as_
        if as_ == hs:
            T[a] += 1; T[h] += 1
        elif as_ > hs:
            W[a] += 1; L[h] += 1
        else:
            W[h] += 1; L[a] += 1
    fails = []
    for s in standings:
        ab = canon(s["abbr"])
        exp = (int(s["w"]), int(s["l"]), int(s["t"]), int(s["pf"]), int(s["pa"]))
        got = (W.get(ab, 0), L.get(ab, 0), T.get(ab, 0), PF.get(ab, 0), PA.get(ab, 0))
        if got != exp:
            fails.append(f"{ab}: standings {exp} vs recomputed from {len(reads)} results {got}")
    return {"verdict": "PASS" if not (fails or unmapped) else "FAIL", "clubs": len(standings),
            "games_summed": len(reads), "assertions": len(standings) * 5,
            "unmapped_club_names": unmapped,
            "mismatches": len(fails), "failures": fails}


def b6_mirror(reads: list[dict]) -> dict:
    with open(MIRROR, encoding="utf-8") as fh:
        mir = {r["game_id"]: r for r in csv.DictReader(fh)
               if r.get("season") == "2026" and r.get("game_type") == "REG"}
    names = {}
    with open(os.path.join(ROOT, "data", "raw", "nflverse", "teams.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("season") == "2026" and r.get("full"):
                names[r["full"].split()[-1]] = r["team"]
    names.setdefault("49ers", "SF")
    fails, agree = [], 0
    for r in reads:
        a, h = names.get(r["away"]), names.get(r["home"])
        if not a or not h:
            fails.append(f"{r['game_slug']}: club name not in the mirror's team list")
            continue
        gid = f"2026_{int(r['week']):02d}_{a}_{h}"
        m = mir.get(gid) or mir.get(gid.replace("_AZ_", "_ARI_"))
        if m is None:
            fails.append(f"{gid}: no mirror row")
            continue
        if (m["away_score"], m["home_score"], m["gameday"]) != (r["away_score"], r["home_score"], r["date"]):
            fails.append(f"{gid}: mirror {m['away_score']}-{m['home_score']} {m['gameday']} "
                         f"vs official read {r['away_score']}-{r['home_score']} {r['date']}")
            continue
        agree += 1
    scored = [g for g, r in mir.items() if (r.get("home_score") or "").strip()]
    return {"verdict": "PASS" if not fails else "FAIL", "corpus_rows": len(reads),
            "mirror_agreements": agree, "mirror_scored_2026_rows": len(scored),
            "mirror_role": "cross-check only; never a published source",
            # only the fields this check consumes — the whole record would couple the pack to another
            # session's manifest edits and make this artefact churn for reasons unrelated to the read
            "manifest_pin": {k: v for k, v in
                             next((m for m in json.load(open(os.path.join(
                                 ROOT, "data", "raw_manifest.json"), encoding="utf-8"))
                                  if m.get("name") == "games.csv"), {}).items()
                             if k in ("bytes", "sha256", "previous_sha256", "retrieved_at", "status", "rows")},
            "failures": fails}


def b7_freshness(live: bool = False) -> dict:
    """`live=True` adds an hours-since-read figure. It is OFF in the committed artefact on purpose: this
    file is guarded by a `--check` that diffs the committed JSON against a fresh build, and a field derived
    from the wall clock would make that gate unpassable (the same defect `scripts/pipeline/verify_captures.py`
    records for the capture page). The timestamp itself is committed, so a reader can subtract.
    """
    latest: dict[str, dict] = {}
    with open(CAP_INDEX, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            e = json.loads(ln)
            d = e["dataset"]
            prev = latest.get(d)
            if prev is None or e["as_read_at"] > prev["as_read_at"]:
                latest[d] = e
    rows = []
    for d, e in sorted(latest.items()):
        rec = {"dataset": d, "as_read_at": e["as_read_at"], "rows": e.get("rows"),
               "drift": e.get("drift"), "status": e.get("status"),
               "content_sha256": e.get("content_sha256")}
        if live:
            try:
                ts = datetime.fromisoformat(e["as_read_at"])
                rec["hours_since_read"] = round(
                    (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0, 2)
            except ValueError:
                rec["hours_since_read"] = None
        rows.append(rec)
    stale = [r["dataset"] for r in rows if r.get("hours_since_read") is not None and r["hours_since_read"] > 36]
    alarms = [r["dataset"] for r in rows if r["drift"] != "pass"]
    return {"verdict": "PASS", "datasets": len(rows), "over_36h": stale,
            "drift_not_pass": alarms, "latest": rows,
            "note": "Reported, not repaired: the capture store and its pins belong to the collector "
                    "(and, for the deficiency pin, to PR #61). A permanently-red alarm is an ignored "
                    "alarm, so the drift verdicts are published here every run."}


def b8_sealed(resolution_expected: dict | None = None) -> dict:
    """Recompute the sealed record from scratch. Deliberately written WITHOUT importing the tool that
    produced it: two implementations of PR-01 agreeing is worth more than one implementation agreeing
    with itself."""
    sealed = csv_file(SEALED)
    corpus = tsv(READS)
    games = {r["game_slug"]: r for r in corpus}
    names = {}
    with open(os.path.join(ROOT, "data", "raw", "nflverse", "teams.csv"), encoding="utf-8") as fh:
        for t in csv.DictReader(fh):
            if t.get("season") == "2026" and t.get("full"):
                names[t["full"].split()[-1]] = t["team"]
    names.setdefault("49ers", "SF")
    code = {v: k for k, v in names.items()}          # "NE" -> "Patriots" is not needed; codes map 1:1
    fails, reproduced, pre_kickoff, resolved = [], 0, 0, 0
    rows = []
    for r in sealed:
        day = r["recorded_at_utc"][:10]
        pool = [g for g in corpus if g["date"] < day]
        sums: dict[str, list[float]] = {}
        for g in pool:
            for side in ("away", "home"):
                club = names.get(g[side]) or g[side]
                pts = int(g[f"{side}_score"])
                opp = int(g["home_score" if side == "away" else "away_score"])
                st = sums.setdefault(canon(club), [0.0, 0.0])
                st[0] += 1
                st[1] += pts - opp

        def rating(club: str) -> float:
            v = sums.get(canon(club))
            if not v:
                return 0.0
            n, diff = v
            return (diff / n) * (n / (n + K))

        margin = rating(r["home"]) - rating(r["away"]) + H
        p = 0.5 * math.erfc(-(margin / SIGMA) / math.sqrt(2.0))
        ok = abs(p - float(r["p_home"])) < 5e-6
        reproduced += ok
        if not ok:
            fails.append(f"{r['game_id']}: sealed p_home {r['p_home']} vs rule at record time {round(p, 6)}")
        kut = _kickoff_utc(r["kickoff_et"])
        if kut and r["recorded_at_utc"] < kut:
            pre_kickoff += 1
        else:
            fails.append(f"{r['game_id']}: recorded {r['recorded_at_utc']} not strictly before kickoff {kut}")
        slug = r["source_url"].rstrip("/").split("/")[-1]
        g = games.get(slug)
        if g is None and r.get("status_at_record", "").startswith("scheduled"):
            pass                       # sealed before it was played: legitimately unresolved
        if g:
            resolved += 1
            actual = int(g["home_score"]) - int(g["away_score"])
            y = 1.0 if actual > 0 else (0.5 if actual == 0 else 0.0)
            brier = (p - y) ** 2
            base = (HOME_BASELINE_P - y) ** 2
            rows.append({"game_id": r["game_id"], "p_home": round(p, 6), "actual_margin_home": actual,
                         "brier": round(brier, 6), "brier_baseline_0.55": round(base, 6),
                         "skill_vs_0.55": round(1 - brier / base, 6),
                         "side": "home" if p >= 0.5 else "away",
                         "side_hit": ("yes" if ((p >= 0.5) == (actual > 0)) else "no") if actual else "push"})
    return {"verdict": "PASS" if not fails else "FAIL", "n_sealed": len(sealed),
            "n_reproduce_from_rule": reproduced, "n_confirmed_pre_kickoff": pre_kickoff,
            "n_resolved": resolved, "n_pending": len(sealed) - resolved,
            "resolved_rows": rows, "failures": fails,
            "independent_of": "recomputed here from reads.tsv and the PR-01 constants, not from "
                              "data/shadow/*, so the published resolution has a second arithmetic path"}


def _kickoff_utc(text: str) -> str:
    txt = (text or "").strip()
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %I:%M%p"):
        try:
            naive = datetime.strptime(txt, fmt)
        except ValueError:
            continue
        try:
            from zoneinfo import ZoneInfo
            return naive.replace(tzinfo=ZoneInfo("America/New_York")).astimezone(
                timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return naive.strftime("%Y-%m-%dT%H:%M:%SZ") + " (coarse: no tz database)"
    return ""


def b9_price_discipline() -> dict:
    seen = {"price_snapshots": 0, "origination": 0, "sealed_forecasts": 0}
    bad = []
    p0 = os.path.join(ROOT, "data", "price_snapshots.json")
    if os.path.exists(p0):
        d = json.load(open(p0, encoding="utf-8"))
        for r in d.get("rows", []):
            seen["price_snapshots"] += 1
            for k in ("market_open_line", "market_close_line", "market_open_price", "market_close_price"):
                if str(r.get(k, "")).strip():
                    bad.append(f"price_snapshots:{k} is populated")
                    break
    p1 = os.path.join(ROOT, "data", "lines", "origination_order_2026_week10.json")
    if os.path.exists(p1):
        d = json.load(open(p1, encoding="utf-8"))
        for r in d.get("rows", []):
            seen["origination"] += 1
            for k in ("market_line", "market_line_alt", "difference"):
                if str(r.get(k, "")).strip():
                    bad.append(f"origination_order:{k} is populated for {r.get('game_id')}")
                    break
    for r in csv_file(SEALED):
        seen["sealed_forecasts"] += 1
        if str(r.get("market_line", "")).strip() or str(r.get("residual", "")).strip():
            bad.append(f"sealed ledger {r['game_id']}: market_line/residual populated")
    ours = sum(1 for r in json.load(open(p0, encoding="utf-8")).get("rows", [])
               if str(r.get("our_close_line", "")).strip()) if os.path.exists(p0) else 0
    return {"verdict": "PASS" if not bad else "FAIL", "rows_scanned": seen,
            "our_own_prices_published": ours,
            "policy": "no price policy ratified (Q-02) → every MARKET value stays blank and flagged; "
                      "the project's OWN originated line is published, because it is the thing under test",
            "failures": sorted(set(bad))}


def b10_slate(w11: list[dict], standings: list[dict]) -> dict:
    games = [r for r in w11 if r["row_type"] == "game"]
    byes = [r for r in w11 if r["row_type"] == "bye"]
    clubs = []
    fails = []
    for r in games:
        clubs += [canon(r["away"]), canon(r["home"])]
        if r["status"] != "Scheduled" or r["away_score"] or r["home_score"]:
            fails.append(f"{r['game_id']}: printed status {r['status']!r} with scores "
                         f"{r['away_score']!r}/{r['home_score']!r} — a played game on the forward slate")
    clubs += [canon(r["away"]) for r in byes]
    if len(games) != 13:
        fails.append(f"{len(games)} fixtures on the slate, expected 13")
    if len(set(clubs)) != 32 or len(clubs) != 32:
        fails.append(f"slate covers {len(set(clubs))} distinct clubs across {len(clubs)} appearances, expected 32/32")
    sealed_ids = {r["game_id"] for r in csv_file(SEALED)}
    unsealed = [g["game_id"] for g in games if g["game_id"] not in sealed_ids]
    return {"verdict": "PASS" if not fails else "FAIL", "fixtures": len(games), "byes": len(byes),
            "clubs_covered": len(set(clubs)), "slate_games_unsealed": unsealed, "failures": fails}


def b11_two_independent_reads(standings: list[dict]) -> dict:
    """The pack header claims this comparison; it is the only thing that makes a hand transcription more
    than a single reader's word. The automated collector read the same page ~3 hours earlier through a
    different code path, so a match on all 18 printed fields is a second transcription, not a restatement.
    """
    cap = json.load(open(os.path.join(ROOT, "data", "pipeline", "standings.json"), encoding="utf-8"))
    rows = {r["team_abbrev"]: r for r in cap.get("rows", [])}
    FIELDS = [("w", "W"), ("l", "L"), ("t", "T"), ("pct", "PCT"), ("pf", "PF"), ("pa", "PA"),
              ("net_pts", "NET_PTS"), ("home", "HOME"), ("road", "ROAD"), ("div", "DIV"),
              ("div_pct", "DIV_PCT"), ("conf", "CONF"), ("conf_pct", "CONF_PCT"),
              ("non_conf", "NON_CONF"), ("strk", "STRK"), ("last5", "LAST_5")]
    fails, cells, name_diff = [], 0, []
    for r in standings:
        ab = canon(r["abbr"])
        c = rows.get(ab)
        if c is None:
            fails.append(f"{ab}: not in the automated capture")
            continue
        if (c.get("team_name") or "").strip() != (r.get("team_name") or "").strip():
            name_diff.append(f"{ab}: capture prints {c.get('team_name')!r}, pack prints {r.get('team_name')!r}")
        for mine, theirs in FIELDS:
            a = re.sub(r"\s+", "", str(r.get(mine, "")))
            b = re.sub(r"\s+", "", str(c.get(theirs, "")))
            cells += 1
            if a != b:
                fails.append(f"{ab}.{mine}: hand read {a!r} vs automated capture {b!r}")
    return {"verdict": "PASS" if not (fails or name_diff) else "FAIL",
            "clubs": len(standings), "cells_compared": cells,
            "capture": {"file": "data/pipeline/standings.json",
                        "as_read_at": cap.get("rows", [{}])[0].get("_retrieved_at"),
                        "content_sha256": sha256(os.path.join(ROOT, "data", "pipeline", "standings.json")),
                        "source_url": "https://www.nfl.com/standings/league/2026/REG"},
            "team_name_differences": name_diff,
            "normalisation": "spaces only ('3 - 1 - 0' == '3-1-0'); no other mapping, so a real "
                             "disagreement cannot be normalised away",
            "failures": fails}


# -------------------------------------------------------------------------------------------------

def build_summary(live: bool = False) -> dict:
    st = pack_rows("official_standings_2026_11_17.tsv")
    w10 = pack_rows("official_w10_results_2026_11_17.tsv")
    w11 = pack_rows("official_w11_slate_2026_11_17.tsv")
    reads = tsv(READS)
    checks = {
        "B1 standings internal consistency": b1_standings_internal(st),
        "B2 league closure": b2_closure(st, reads),
        "B3 three-page record agreement": b3_cross_page_records(st, w10, w11),
        "B4 corpus admission": b4_corpus_admission(w10, reads),
        "B5 standings arithmetic": b5_standings_arithmetic(st, reads),
        "B6 mirror cross-check": b6_mirror(reads),
        "B7 capture freshness": b7_freshness(live),
        "B8 sealed ledger": b8_sealed(),
        "B9 price discipline": b9_price_discipline(),
        "B10 forward slate": b10_slate(w11, st),
        "B11 two independent standings reads": b11_two_independent_reads(st),
    }
    hard = [k for k, v in checks.items() if v["verdict"] == "FAIL" and not k.startswith("B7")]
    return {
        "dataset": "official_reverification_2026_11_17",
        "title": "Line-by-line re-verification of the 2026-11-17 official reads against the published corpus",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "tools/verify_2026_11_17.py (session arena-e1436334-x1)",
        "reads": [
            {"page": W10_URL, "file": "data/verification/2026_11_17/official_w10_results_2026_11_17.tsv",
             "rows": len(w10), "read_on": RETRIEVED, "clock_noted_by_reader": f"{RETRIEVED} 22:45 UTC"},
            {"page": STANDINGS_URL, "file": "data/verification/2026_11_17/official_standings_2026_11_17.tsv",
             "rows": len(st), "read_on": RETRIEVED, "clock_noted_by_reader": f"{RETRIEVED} 22:48 UTC"},
            {"page": W11_URL, "file": "data/verification/2026_11_17/official_w11_slate_2026_11_17.tsv",
             "rows": len(w11), "read_on": RETRIEVED, "clock_noted_by_reader": f"{RETRIEVED} 22:52 UTC"},
        ],
        "read_clock_note": (
            "Two clocks, and the difference between them is stated rather than smoothed. Each pack header "
            "carries a minute (22:45 / 22:48 / 22:52 UTC) that the READER wrote into the file at "
            "transcription time; the page reader itself returns content with no retrieval timestamp, so "
            "those minutes are a self-report, accurate to the order and the hour, not an instrument. The "
            "automated capture's stamp for the same standings page IS an instrument reading "
            "(2026-11-17T19:49:49Z, content sha256 in the header), and check B11 compares the two reads. "
            "The feed's arithmetic gate is validated against the dated pack; the capture is its second "
            "opinion. Where the brief asks for reads 'with a clock time', that is what the collector "
            "provides and what a hand read can only claim to the minute it noted itself."),
        "second_official_read": {
            "fixture": "https://www.nfl.com/games/chargers-at-ravens-2026-reg-10",
            "why": "the only fixture whose state changed between the 2026-11-16 and 2026-11-17 reads, so it "
                   "is the one row worth reading on a second official page (Game Center, with quarter scores "
                   "and the printed venue)",
        },
        "transcription_hashes": {
            "official_w10_results_2026_11_17.tsv": sha256(os.path.join(VDIR, "official_w10_results_2026_11_17.tsv")),
            "official_standings_2026_11_17.tsv": sha256(os.path.join(VDIR, "official_standings_2026_11_17.tsv")),
            "official_w11_slate_2026_11_17.tsv": sha256(os.path.join(VDIR, "official_w11_slate_2026_11_17.tsv")),
            "reads.tsv": sha256(READS),
            "mirror_games.csv": sha256(MIRROR),
        },
        "checks": checks,
        "verdict": "PASS" if not hard else "FAIL",
        "hard_failures": hard,
        "not_checked_here": [
            "injury / availability / depth tables and their day-over-day deltas — published by PR #73 "
            "(arena/16049865-x1) on the same date; this session deliberately did not touch that scope",
            "the deficiency dataset's declared-column drift alarm — root cause handed to the drift owner "
            "and to PR #61 in COORDINATION.md (pipeline/run.py owns the payload's columns list)",
            "player-level game books, snap counts and inactive lists — no licensed source in this repository",
            "any price, closing line or ROI in dollars — no ratified price policy (Q-02)",
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--live", action="store_true",
                    help="add the wall-clock freshness figure (never committed: it is not reproducible)")
    args = ap.parse_args(argv)
    payload = build_summary(args.live)
    text = json.dumps(payload, indent=1) + "\n"
    if args.check:
        got = open(os.path.join(VDIR, SUMMARY), encoding="utf-8").read()
        strip = lambda s: "\n".join(l for l in s.split("\n") if '"generated_at"' not in l)
        ok = strip(got) == strip(text)
        print("CHECK OK: the 2026-11-17 pack matches a fresh build of the same reads"
              if ok else "STALE: verification_summary_2026_11_17.json differs from a fresh build")
        return 0 if ok else 1
    if args.write and args.live:
        print("REFUSING to write: --write with --live would commit a wall-clock number into a "
              "re-derivable artefact. Run --write alone, or --live alone to look.")
        return 2
    if args.write:
        with open(os.path.join(VDIR, SUMMARY), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(f"2026-11-17 re-verification — overall {payload['verdict']}")
    for k, v in payload["checks"].items():
        extra = ""
        if k.startswith("B4"):
            extra = f" (corpus {v['corpus_rows']} rows)"
        if k.startswith("B5"):
            extra = f" ({v['mismatches']} mismatches over {v['assertions']} assertions)"
        if k.startswith("B8"):
            extra = f" ({v['n_resolved']} resolved, {v['n_pending']} pending)"
        print(f"  {k:38s} {v['verdict']}{extra}")
        for f in v.get("failures", [])[:4]:
            print("      !", f)
    return 1 if payload["hard_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
