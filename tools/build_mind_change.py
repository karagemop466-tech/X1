#!/usr/bin/env python3
"""Two-sided mind-change register: what would make us adopt, and what would make us abandon, each strategy.

    python3 tools/build_mind_change.py            # write
    python3 tools/build_mind_change.py --check    # fail if the committed files are stale

The brief asks for "a two-sided 'what would change our mind' field to every strategy entry". Each
published strategy table carries at most one side — the lab leaderboard carries a `falsifier` and
the console strategy table carries neither — and no entry states the sample that would settle it.
This builder writes both sides for every entry in both tables, as arithmetic, under the rule frozen
in `docs/preregistration/MIND-CHANGE-01.md`, whose SHA-256 is published with every number. The
verifier (`tools/verify_mind_change.py`) recomputes the arithmetic from the inputs and fails if the
rule file no longer hashes to what the rows cite.

Inputs are read, never rewritten:
  data/console/strategy_results.csv        16 published strategy entries, with their own CI on the edge
  data/lab/leaderboard.json                 8 evaluated entries, with a CI on the hit rate
  data/preregistration/register.json        the four registered rules, whose mind-change is about the rule
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

Z = 1.959963985          # two-sided 95%, used per rule section 7
BREAKEVEN_110 = 0.5238095238095238


def verdict_name(lo, hi):
    return "ADOPT" if lo > 0 else "ABANDON" if hi < 0 else "undecided"


def evaluate(p_hat, n, p0, edge_lo=None, edge_hi=None):
    """Both sides, per MIND-CHANGE-01. The published interval decides; the register's own is the check.

    `edge_lo`/`edge_hi` are the entry table's own 95% interval on (rate - bar). When they are absent
    the register's recomputed normal-approximation interval is used, and the row says so.
    """
    if not n or p_hat is None:
        return dict(state="no sample", basis="none: zero decided bets",
                    adopt_if="not evaluable on this test - the entry has no decided bets, which is "
                             "itself the finding the gates already record",
                    abandon_if="not evaluable on this test either - a missing feed cannot be abandoned "
                               "by an interval, only by the source question that blocks it",
                    bets_to_adopt="", bets_to_abandon="", rate_to_adopt="",
                    lower_bound="", upper_bound="", half_width="", no_n_note="",
                    interval_disagreement="")
    half = Z * math.sqrt(max(p_hat * (1 - p_hat), 1e-12) / n)
    edge = p_hat - p0
    own_lo, own_hi = edge - half, edge + half
    lo, hi = (edge_lo, edge_hi) if edge_lo is not None and edge_hi is not None else (own_lo, own_hi)
    basis = ("the entry table's own published interval" if edge_lo is not None
             else "this register's normal-approximation interval (the table publishes none)")
    adopt_now, abandon_now = lo > 0, hi < 0
    disagree = ((own_lo > 0) != (lo > 0)) or ((own_hi < 0) != (hi < 0)) if edge_lo is not None else False
    gap = abs(edge)
    if gap < 1e-12:
        to_adopt = to_abandon = ""
        no_n = "the observed rate equals the bar exactly; no sample separates them"
    else:
        n_star = int(math.ceil((Z / gap) ** 2 * p_hat * (1 - p_hat)))
        to_adopt, to_abandon = ((n_star, "") if edge > 0 else ("", n_star))
        no_n = ("" if edge > 0 else
                "no n exists at this rate: the observed rate is below the bar, so more of the same "
                "data can only confirm abandonment, never promotion")
    p_star = p0 + Z * math.sqrt(p0 * (1 - p0) / n)
    adopt_txt = ("already clear of the bar: the published lower bound is "
                 f"{lo:+.4f} against a bar of {p0:.4f}" if adopt_now else
                 (f"{to_adopt:,} more decided bets at the observed {p_hat:.4f}"
                  if edge > 0 else no_n))
    abandon_txt = (f"already under the bar: the published upper bound is {hi:+.4f}"
                   if abandon_now else
                   (f"{to_abandon:,} more decided bets at the observed {p_hat:.4f} would put the "
                    f"whole interval under the bar" if edge < 0 else
                    "no n exists at this rate that abandons this entry: the interval sits above the "
                    "bar, so only the eight gates can close it"))
    if disagree:
        note = ("suspended: the interval the entry's own table publishes reads as "
                f"{verdict_name(lo, hi)} while this register's normal-approximation interval "
                f"reads as {verdict_name(own_lo, own_hi)} - the claim is withheld here until the "
                "interval method is reconciled at the source")
        adopt_if = abandon_if = note
    else:
        adopt_if = adopt_txt
        abandon_if = abandon_txt
    return dict(
        state=("interval methods disagree" if disagree else
               "ADOPT-eligible on this test" if adopt_now else
               "ABANDON-eligible on this test" if abandon_now else "undecided"),
        basis=basis,
        adopt_if=adopt_if, abandon_if=abandon_if,
        # a suspended row carries no to-do sample either: the claim itself is suspended
        bets_to_adopt="" if (adopt_now or disagree) else to_adopt,
        bets_to_abandon="" if (abandon_now or disagree) else to_abandon,
        rate_to_adopt=round(p_star, 4),
        published_interval=(f"{lo:+.4f} to {hi:+.4f}" if edge_lo is not None else "none published"),
        own_interval=f"{own_lo:+.4f} to {own_hi:+.4f}",
        lower_bound=round(lo, 5), upper_bound=round(hi, 5), half_width=round(half, 5),
        no_n_note=no_n,
        interval_disagreement=("published interval and the register's own recomputation give "
                               "different verdicts - no mind-change claim is made on this row"
                               if disagree else ""),
    )


def _rows_strategy_results():
    out = []
    with open(os.path.join(D, "console", "strategy_results.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            p = float(r["HIT_RATE"]) if r["HIT_RATE"] else None
            n = int(r["BETS"]) if r["BETS"] else 0
            p0 = float(r["BREAKEVEN_HIT_RATE"]) if r["BREAKEVEN_HIT_RATE"] else BREAKEVEN_110
            lo = float(r["CI_LOW"]) if r["CI_LOW"] else None
            hi = float(r["CI_HIGH"]) if r["CI_HIGH"] else None
            out.append(dict(
                entry_id=r["ID"], name=f'{r["FAMILY"]} ({r["PARAM"]})', table="strategy_results.csv",
                division=r["FAMILY"], shape="flat", market=r["PARAM"],
                hypothesis=r["RULE"], falsifier_on_file="none recorded in that table",
                bar_type="the break-even its own published price implies",
                n_decided=n, hit_rate=p, break_even=round(p0, 6),
                _lo=lo, _hi=hi,
                signal_score=r["SIGNAL_SCORE"], staking_score=r["STAKING_SCORE"],
                promoted=r["PROMOTED"], p_value=r["P_VALUE"],
                source_url=r["SOURCE"],
            ))
    return out


def _rows_leaderboard():
    lab = json.load(open(os.path.join(D, "lab", "leaderboard.json"), encoding="utf-8"))
    out = []
    for r in lab["rows"]:
        sig = r.get("signal") or {}
        p = sig.get("hit_rate")
        n = sig.get("decided") or sig.get("n") or 0
        p0 = sig.get("break_even_hit_rate") or BREAKEVEN_110
        ci = sig.get("hit_rate_ci95") or []
        lo = (float(ci[0]) - float(p0)) if len(ci) == 2 else None
        hi = (float(ci[1]) - float(p0)) if len(ci) == 2 else None
        out.append(dict(
            entry_id=r["id"], name=r["name"], table="leaderboard.json",
            division=r.get("division", ""), shape=r.get("shape", ""), market=r.get("market", ""),
            hypothesis=r.get("hypothesis", ""), falsifier_on_file=r.get("falsifier", ""),
            bar_type=("the compounded bar its legs imply, under the entry's own correlation "
                      "adjustment" if r.get("shape") in ("parlay", "combo")
                      else "the -110 break-even"),
            n_decided=int(n), hit_rate=float(p) if p is not None else None,
            break_even=round(float(p0), 6), _lo=lo, _hi=hi,
            signal_score="", staking_score="", promoted="",
            p_value=sig.get("p_value", ""),
            gates_passed=r.get("gates_passed"), gates_failed=r.get("gates_failed"),
            demotion=str(r.get("demotion", "")), status=r.get("status", ""),
            source_url=("https://github.com/karagemop466-tech/X1/blob/main/data/lab/"
                        "leaderboard.json"),
        ))
    return out


def build():
    rule_bytes = open(RULE, "rb").read()
    rule_sha = hashlib.sha256(rule_bytes).hexdigest()
    pre = json.load(open(os.path.join(D, "preregistration", "register.json"), encoding="utf-8"))

    rows = [_finish(src, rule_sha)
            for src in _rows_strategy_results() + _rows_leaderboard()]

    # the four registered rules: a rule's mind-change is about its registration, not a hit rate
    for pid, pr in {r["id"]: r for r in pre["rows"]}.items():
        gates = pr.get("gates")
        gates = "; ".join(gates) if isinstance(gates, list) else str(gates or "")
        broken = pr.get("rule_hash_matches_this_checkout") is False
        rows.append(dict(
            entry_id=pid, name=pr["name"], table="preregistration/register.json",
            division="registration", shape="rule", market=str(pr.get("markets", "")),
            hypothesis=str(pr.get("window", "")),
            falsifier_on_file=gates,
            bar_type="the rule's own registered gates",
            n_decided="", hit_rate="", break_even="",
            state="rule at risk" if broken else "rule holds",
            basis="the registered rule bytes and their hash, not an interval",
            adopt_if=("confirmed when the gates it registered for itself pass, on its own window: "
                      + gates),
            abandon_if=("the rule's own text no longer hashes to its registration - a broken "
                        "registration, not a finding" if broken else
                        "the rule is found to have been edited after its window opened, or its "
                        "registered gates fail on their own window"),
            bets_to_adopt="", bets_to_abandon="", rate_to_adopt="",
            lower_bound="", upper_bound="", half_width="",
            no_n_note="", interval_disagreement="",
            signal_score="", staking_score="", promoted="", p_value="",
            gates_passed="", gates_failed="", demotion="", status=pr.get("state", ""),
            registration="MIND-CHANGE-01", rule_sha256=rule_sha, registered_at_utc="2026-11-18",
            source_url=("https://github.com/karagemop466-tech/X1/blob/main/data/preregistration/"
                        "register.json"),
            notes=("registration commit "
                   + (pr.get("registration_commit") or "unresolved in a shallow checkout")
                   + "; content hash match: " + str(pr.get("content_hash_matches_registration"))),
        ))
    for r in rows:
        r.setdefault("notes", "")
        if r["table"] == "strategy_results.csv":
            r["notes"] = ("this table publishes no falsifier field, so both sides come from this "
                          "register; n* is a lower bound because the table's interval is wider than "
                          "the normal approximation")
        elif r["interval_disagreement"]:
            r["notes"] = r["interval_disagreement"]
        elif r["shape"] in ("parlay", "combo"):
            r["notes"] = ("the parlay bar is the product of its legs' break-evens under the entry's "
                          "own correlation adjustment; a joint probability has not been validated "
                          "directly, which is why this row is descriptive")
        else:
            r["notes"] = ("hit-rate test only: ROI needs a price and no licensed price source exists "
                          "(Q-02)")

    strat = [r for r in rows if r["division"] != "registration"]
    summary = dict(
        dataset="mind_change",
        title="Two-sided mind-change register: every strategy entry's adopt test and its abandon test",
        generated_by="tools/build_mind_change.py",
        rule=dict(file="docs/preregistration/MIND-CHANGE-01.md", sha256=rule_sha,
                  registered_at_utc="2026-11-18",
                  how_to_verify="python3 tools/verify_mind_change.py"),
        definitions=dict(
            adopt="the entry's published 95% interval on (rate - bar) lies entirely above zero",
            abandon="that interval lies entirely below zero",
            basis=("the interval is the one the entry's own table publishes; strategy_results.csv "
                   "publishes CI_LOW/CI_HIGH on the edge scale, the lab leaderboard publishes "
                   "hit_rate_ci95 on the rate scale, converted here against the same bar"),
            bets_to_adopt=("n* = ceil((z/|p-p0|)^2 * p(1-p)) at the observed rate - the sample that "
                           "would clear the bar without the rate moving; a lower bound where the "
                           "published interval is wider than the normal approximation"),
            rate_to_adopt=f"p* = p0 + z*sqrt(p0(1-p0)/n) - the rate that clears the bar at today's n",
            no_n=("when the observed rate is on the wrong side of the bar, more data cannot promote "
                  "the entry, and the register says that instead of printing a large n"),
        ),
        counts=dict(
            entries=len(rows),
            from_strategy_results=len([r for r in rows if r["table"] == "strategy_results.csv"]),
            from_leaderboard=len([r for r in rows if r["table"] == "leaderboard.json"]),
            rule_rows=len([r for r in rows if r["division"] == "registration"]),
            both_sides_published=len([r for r in strat if r["adopt_if"] and r["abandon_if"]]),
            already_had_one_side=len([r for r in rows
                                      if r["falsifier_on_file"] not in ("", "none recorded in that table")]),
            undecided=len([r for r in rows if r["state"] == "undecided"]),
            adopt_eligible=len([r for r in rows if r["state"].startswith("ADOPT")]),
            abandon_eligible=len([r for r in rows if r["state"].startswith("ABANDON")]),
            no_sample=len([r for r in rows if r["state"] == "no sample"]),
            interval_methods_disagree=len([r for r in rows if r["interval_disagreement"]]),
            adoption_unreachable_at_observed_rate=len([r for r in rows if r["no_n_note"]]),
        ),
        caveats=[
            "This register publishes only the mind-change fields. Promotion still requires the eight "
            "validation gates; nothing here moves a strategy's status, and no entry on this board is "
            "promoted.",
            "The verdict is read off the interval each table already publishes, so this register can "
            "never disagree with the leaderboard page a reader can open. Where the register's own "
            "normal-approximation interval would give a different verdict, the row is flagged and no "
            "claim is made.",
            "n* is computed under the normal approximation and is a lower bound wherever the "
            "published interval is wider; it is the sample needed at the observed rate, not a "
            "guarantee of the same rate.",
            "The Week 11 slate had not kicked off when this was registered (2026-11-18), so no row "
            "here was written with knowledge of a Week 11 result; the chronology is check F of "
            "tools/verify_mind_change.py.",
        ],
    )
    return rows, summary


def _finish(src, rule_sha):
    """Apply the rule to one table row, then fill the columns the other table does not carry."""
    p, n, p0 = src["hit_rate"], src["n_decided"], src["break_even"]
    r = dict(src)
    lo, hi = r.pop("_lo", None), r.pop("_hi", None)
    r.update(evaluate(p, n, p0, lo, hi))
    r["registration"] = "MIND-CHANGE-01"
    r["rule_sha256"] = rule_sha
    r["registered_at_utc"] = "2026-11-18"
    r.setdefault("gates_passed", "")
    r.setdefault("gates_failed", "")
    r.setdefault("demotion", "")
    r.setdefault("status", "")
    r.setdefault("signal_score", "")
    r.setdefault("staking_score", "")
    r.setdefault("promoted", "")
    r.setdefault("p_value", "")
    return r


COLS = ["entry_id", "name", "table", "division", "shape", "market", "hypothesis",
        "falsifier_on_file", "bar_type", "n_decided", "hit_rate", "break_even", "state", "basis",
        "adopt_if", "abandon_if", "bets_to_adopt", "bets_to_abandon", "rate_to_adopt",
        "published_interval", "own_interval", "lower_bound", "upper_bound", "half_width",
        "no_n_note", "interval_disagreement",
        "signal_score", "staking_score", "p_value", "promoted", "gates_passed", "gates_failed",
        "demotion", "status", "registration", "rule_sha256", "registered_at_utc", "source_url",
        "notes"]


def write(rows, summary, check=False):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLS)
    for r in rows:
        w.writerow([r.get(c, "") for c in COLS])
    # the rule text ships beside the register it governs, byte for byte, so the published page can
    # link the rule it was built under (and so the staleness check covers the copy too)
    files = {"register.csv": buf.getvalue(),
             "summary.json": json.dumps(summary, indent=1) + "\n",
             "MIND-CHANGE-01.md": open(RULE, encoding="utf-8").read()}
    if check:
        bad = [n for n, t in files.items()
               if not os.path.exists(os.path.join(OUT, n))
               or open(os.path.join(OUT, n), encoding="utf-8").read() != t]
        if bad:
            print("[mind-change] STALE: " + ", ".join(bad))
            return 1
        print(f"[mind-change] current: {len(rows)} entries")
        return 0
    os.makedirs(OUT, exist_ok=True)
    for n, t in files.items():
        with open(os.path.join(OUT, n), "w", encoding="utf-8") as fh:
            fh.write(t)
    c = summary["counts"]
    print(f"[mind-change] wrote {c['entries']} entries ({c['from_strategy_results']} from the "
          f"strategy table, {c['from_leaderboard']} from the leaderboard, {c['rule_rows']} rules): "
          f"{c['undecided']} undecided, {c['abandon_eligible']} already past the abandon bound, "
          f"{c['adoption_unreachable_at_observed_rate']} unreachable at their observed rate")
    return 0


if __name__ == "__main__":
    sys.exit(write(*build(), check="--check" in sys.argv))
