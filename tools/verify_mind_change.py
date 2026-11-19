#!/usr/bin/env python3
"""Verify the two-sided mind-change register: arithmetic recomputed, rule hash pinned, chronology checked.

    python3 tools/verify_mind_change.py

The point of a mind-change register is that nobody can move the goalposts once the results are in, so
this verifier recomputes every number from the upstream tables instead of trusting the register:

  A  the frozen rule file's SHA-256 still matches what every row and the summary cite
  B  every strategy entry carries BOTH sides - an adopt test and an abandon test (the one-sided field
     is the defect this register exists to fix)
  C  the arithmetic, recomputed independently from data/console/strategy_results.csv and
     data/lab/leaderboard.json: interval bounds, verdict, n* and p*, and the disagreement flag
  D  no entry is called adopt-eligible while its own gates are failing, and no entry that the
     published interval already puts under the bar is described as merely undecided
  E  the summary's counts agree with its rows
  F  chronology: registered_at precedes the first Week 11 kickoff, so no row was written knowing a
     Week 11 result
  G  the published files are byte-for-byte what the builder writes (staleness)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
OUT = os.path.join(D, "mind_change")
RULE = os.path.join(ROOT, "docs", "preregistration", "MIND-CHANGE-01.md")
Z = 1.959963985
BREAKEVEN_110 = 0.5238095238095238


def verdict_from(lo, hi):
    return ("ADOPT" if lo > 0 else "ABANDON" if hi < 0 else "undecided")


def main():
    fails, notes = [], []
    reg_path = os.path.join(OUT, "register.csv")
    if not os.path.exists(reg_path):
        print("FAIL: no mind-change register built yet (python3 tools/build_mind_change.py)")
        return 1
    rows = list(csv.DictReader(open(reg_path, encoding="utf-8")))
    summ = json.load(open(os.path.join(OUT, "summary.json"), encoding="utf-8"))

    # ---- A: the rule file is the one the rows cite --------------------------------
    sha = hashlib.sha256(open(RULE, "rb").read()).hexdigest()
    cited = {r["rule_sha256"] for r in rows}
    if cited != {sha}:
        fails.append(f"A: the register cites {len(cited)} distinct rule hash(es) and the file on disk "
                     f"is {sha[:12]} - a threshold edited after the results are in is not a threshold")
    elif summ["rule"]["sha256"] != sha:
        fails.append("A: summary.json records a different rule hash from the rows")
    else:
        notes.append(f"A: all {len(rows)} rows and the summary cite the rule file on disk "
                     f"({sha[:12]})")

    # ---- B: two-sided -------------------------------------------------------------
    one_sided = [(r["entry_id"], "abandon" if not (r["abandon_if"] or "").strip() else "adopt")
                 for r in rows
                 if not (r["adopt_if"] or "").strip() or not (r["abandon_if"] or "").strip()]
    if one_sided:
        fails.append(f"B: {len(one_sided)} entries publish only one side: "
                     + "; ".join(f"{i} lacks {s}" for i, s in one_sided[:6]))
    else:
        notes.append(f"B: {len(rows)} entries, each with an adopt test and an abandon test")

    # ---- C: recompute both upstream tables independently ---------------------------
    expect = {}
    with open(os.path.join(D, "console", "strategy_results.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            p = float(r["HIT_RATE"]) if r["HIT_RATE"] else None
            n = int(r["BETS"]) if r["BETS"] else 0
            p0 = float(r["BREAKEVEN_HIT_RATE"]) if r["BREAKEVEN_HIT_RATE"] else BREAKEVEN_110
            expect[r["ID"]] = (p, n, p0,
                               float(r["CI_LOW"]) if r["CI_LOW"] else None,
                               float(r["CI_HIGH"]) if r["CI_HIGH"] else None)
    lab = json.load(open(os.path.join(D, "lab", "leaderboard.json"), encoding="utf-8"))
    for r in lab["rows"]:
        sig = r.get("signal") or {}
        ci = sig.get("hit_rate_ci95") or []
        p0 = float(sig.get("break_even_hit_rate") or BREAKEVEN_110)
        expect[r["id"]] = (float(sig["hit_rate"]) if sig.get("hit_rate") is not None else None,
                           int(sig.get("decided") or sig.get("n") or 0), p0,
                           (float(ci[0]) - p0) if len(ci) == 2 else None,
                           (float(ci[1]) - p0) if len(ci) == 2 else None)

    checked = 0
    for r in rows:
        e = expect.get(r["entry_id"])
        if not e:
            if r["division"] != "registration":
                fails.append(f"C: register row {r['entry_id']} matches no entry in either upstream "
                             f"table - an orphan is not coverage")
            continue
        p, n, p0, lo, hi = e
        if not n or p is None:
            if r["state"] != "no sample":
                fails.append(f"C: {r['entry_id']} has zero decided bets but is published as "
                             f"{r['state']!r}")
            continue
        checked += 1
        if int(r["n_decided"]) != n or abs(float(r["hit_rate"]) - p) > 1e-9:
            fails.append(f"C: {r['entry_id']} n/hit rate disagree with the upstream table "
                         f"({r['n_decided']}, {r['hit_rate']}) vs ({n}, {p})")
        own_half = Z * math.sqrt(max(p * (1 - p), 1e-12) / n)
        own = (p - p0 - own_half, p - p0 + own_half)
        use = (lo, hi) if lo is not None and hi is not None else own
        want = verdict_from(*use)
        own_v = verdict_from(*own)
        want_disagree = lo is not None and hi is not None and own_v != want
        # rule section 7: a disagreement between interval methods suspends the claim
        if want_disagree:
            want = "interval methods disagree"
        got = ("ADOPT" if r["state"].startswith("ADOPT")
               else "ABANDON" if r["state"].startswith("ABANDON") else r["state"])
        if got != want:
            fails.append(f"C: {r['entry_id']} state {r['state']!r} but recomputed {want!r} from its "
                         f"own published interval {use[0]:+.4f}/{use[1]:+.4f} (bar {p0:.4f}, the "
                         f"register's own interval gives {own_v})")
        if bool(r["interval_disagreement"]) != want_disagree:
            fails.append(f"C: {r['entry_id']} disagreement flag "
                         f"{'set' if r['interval_disagreement'] else 'clear'} but the published "
                         f"interval gives {verdict_from(*use)} and the register's own gives {own_v}")
        gap = abs(p - p0)
        if gap > 1e-12:
            n_star = int(math.ceil((Z / gap) ** 2 * p * (1 - p)))
            field, other = (("bets_to_adopt", "bets_to_abandon") if p > p0
                            else ("bets_to_abandon", "bets_to_adopt"))
            if want == "interval methods disagree":
                for f in ("adopt_if", "abandon_if"):
                    if "suspended" not in r[f]:
                        fails.append(f"C: {r['entry_id']} suspends the verdict but {f} still reads "
                                     f"{r[f][:60]!r}")
                for f in ("bets_to_adopt", "bets_to_abandon"):
                    if r[f]:
                        fails.append(f"C: {r['entry_id']} suspends its claim on the interval "
                                     f"disagreement yet still publishes {f}={r[f]}")
            if want in ("ADOPT", "ABANDON"):
                for f in (field, other):
                    if r[f] not in ("", "0"):
                        fails.append(f"C: {r['entry_id']} is {want} on this test yet publishes {f}"
                                     f"={r[f]}; a settled entry must not carry a to-do sample")
            elif want == "undecided" and r[field] != str(n_star):
                fails.append(f"C: {r['entry_id']} {field}={r[field]!r} but the rule gives {n_star:,} "
                             f"more decided bets at the observed rate")
            if p < p0 and not r["no_n_note"]:
                fails.append(f"C: {r['entry_id']} sits below its bar with no adoption possible, but "
                             f"the register does not say so")
        p_star = p0 + Z * math.sqrt(p0 * (1 - p0) / n)
        if r["rate_to_adopt"] and abs(float(r["rate_to_adopt"]) - p_star) > 5e-4:
            fails.append(f"C: {r['entry_id']} rate_to_adopt {r['rate_to_adopt']} vs recomputed "
                         f"{p_star:.4f}")

    n_disagree = len([r for r in rows if r["interval_disagreement"]])
    notes.append(f"C: {checked} entries recomputed from their own tables - intervals, verdicts, n* "
                 f"and p*; {n_disagree} flagged because the table's published interval and the "
                 f"register's normal approximation give different verdicts (no claim made on those)")

    # ---- D: claims against the gates, and the abandoned entries ---------------------
    adopt_gated = [r["entry_id"] for r in rows
                   if r["state"].startswith("ADOPT") and str(r["gates_failed"] or "0") not in ("0", "")]
    if adopt_gated:
        fails.append(f"D: adopt-eligible while gates are failing: {adopt_gated}")
    promoted = [r["entry_id"] for r in rows if str(r["promoted"]).lower() == "true"]
    if promoted:
        fails.append(f"D: the register marks a promoted entry ({promoted}) as though promotion were "
                     f"still an open question - re-check which table this came from")
    aband = [r for r in rows if r["state"].startswith("ABANDON")]
    still_alive = [r["entry_id"] for r in aband
                   if r["falsifier_on_file"] and r["falsifier_on_file"] != "none recorded in that table"
                   and "not " in r["falsifier_on_file"].lower()]
    notes.append(f"D: {len(aband)} entries are already past their abandon bound "
                 f"({', '.join(r['entry_id'] for r in aband)}); none is promoted, and no row claims "
                 f"adoption while a gate fails")
    if still_alive:
        notes.append(f"D: {len(still_alive)} of those had a falsifier on file that names this exact "
                     f"condition ({', '.join(still_alive)}) - the falsifier has fired and the entry "
                     f"is still open on the board")

    # ---- E: counts ------------------------------------------------------------------
    c = summ["counts"]
    strat = [r for r in rows if r["division"] != "registration"]
    want_c = dict(
        entries=len(rows),
        from_strategy_results=len([r for r in rows if r["table"] == "strategy_results.csv"]),
        from_leaderboard=len([r for r in rows if r["table"] == "leaderboard.json"]),
        rule_rows=len([r for r in rows if r["division"] == "registration"]),
        both_sides_published=len([r for r in strat if r["adopt_if"] and r["abandon_if"]]),
        undecided=len([r for r in rows if r["state"] == "undecided"]),
        adopt_eligible=len([r for r in rows if r["state"].startswith("ADOPT")]),
        abandon_eligible=len([r for r in rows if r["state"].startswith("ABANDON")]),
        no_sample=len([r for r in rows if r["state"] == "no sample"]),
        interval_methods_disagree=len([r for r in rows if r["interval_disagreement"]]),
        adoption_unreachable_at_observed_rate=len([r for r in rows if r["no_n_note"]]),
    )
    for k, v in want_c.items():
        if int(c.get(k, -1)) != v:
            fails.append(f"E: summary counts[{k!r}]={c.get(k)} but the rows hold {v}")
    cover = want_c["from_strategy_results"] + want_c["from_leaderboard"]
    if cover != len(expect):
        fails.append(f"E: the register covers {cover} strategy entries but the two tables publish "
                     f"{len(expect)} between them - the brief says every entry")
    if not fails:
        notes.append(f"E: counts agree, and coverage is complete - {want_c['from_strategy_results']} "
                     f"of {want_c['from_strategy_results']} from the strategy table, "
                     f"{want_c['from_leaderboard']} of {want_c['from_leaderboard']} from the "
                     f"leaderboard, {want_c['rule_rows']} registered rules")

    # ---- F: chronology --------------------------------------------------------------
    reg = summ["rule"]["registered_at_utc"]
    first = None
    esc = os.path.join(D, "lab", "escrow", "week11_forecasts_2026-11-17.csv")
    if os.path.exists(esc):
        kick = [r["kickoff_utc"] for r in csv.DictReader(open(esc, encoding="utf-8"))
                if r.get("kickoff_utc")]
        first = min(kick) if kick else None
    if first is None:
        fails.append("F: no Week 11 kickoff found, so the registration cannot be shown to precede the "
                     "week - and that chronology is the point of registering the rule in advance")
    elif not (reg <= first[:10]):
        fails.append(f"F: register says {reg}, which is after the first Week 11 kickoff ({first})")
    else:
        notes.append(f"F: registered {reg}, before the first Week 11 kickoff at {first} - no row "
                     f"here was written knowing a Week 11 result")

    # ---- G: staleness ---------------------------------------------------------------
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import build_mind_change as B  # noqa: E402
    exp_rows, exp_summ = B.build()
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(B.COLS)
    for r in exp_rows:
        w.writerow([r.get(x, "") for x in B.COLS])
    stale = []
    if open(reg_path, encoding="utf-8").read() != buf.getvalue():
        stale.append("register.csv")
    if (open(os.path.join(OUT, "summary.json"), encoding="utf-8").read()
            != json.dumps(exp_summ, indent=1) + "\n"):
        stale.append("summary.json")
    # the rule copy shipped beside the register must be the rule the pages link
    if (open(os.path.join(OUT, "MIND-CHANGE-01.md"), encoding="utf-8").read()
            != open(RULE, encoding="utf-8").read()):
        stale.append("MIND-CHANGE-01.md (the shipped copy differs from docs/preregistration/)")
    if stale:
        fails.append(f"G: STALE - {' and '.join(stale)} differ from a fresh build (run "
                     f"python3 tools/build_mind_change.py)")
    else:
        notes.append("G: the register is byte-for-byte what the builder writes from its inputs")

    print(f"[mind-change] {len(notes) + len(fails)} checks run")
    for n in notes:
        print("  ", n)
    if fails:
        print("\nFAIL")
        for f in fails:
            print("  -", f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
