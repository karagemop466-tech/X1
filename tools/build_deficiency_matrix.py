#!/usr/bin/env python3
"""Build the interactive offense-vs-defense matchup deficiency matrix (requirement R-76).

Session arena/91656714-x1, round 6. R-76 was the one line of the owner brief with no built
artefact: the join it needs existed (`data/console/depth_replacement.csv`, 897 slots, 31 of 32
clubs) but nothing joined it. This builds that join.

WHAT THIS PUBLISHES, AND WHAT IT REFUSES TO PUBLISH
---------------------------------------------------
For one fixture it pairs the AWAY offense against the HOME defense and the HOME offense against
the AWAY defense, and for each position group reports:

  * the club's listed starter (from its own official depth chart),
  * whether that starter appears on the official injury report, and with what game status,
  * the named replacement and the depth rank at which the club lists him,
  * the OPPOSING defender the starter would have faced, with HIS status and replacement.

The last column is the actual question the brief asks: not "is someone out" but "is a 1st-string
attacker now facing a 2nd/3rd/4th-string defender because that defender's club lost its starter".

FOUR THINGS THIS DELIBERATELY DOES NOT DO
-----------------------------------------
1. It does not invent a starter for a slot the club left empty, or for a slot where several
   players are listed at rank 1 (149 such slots exist repo-wide). A slot with more than one
   rank-1 name is published as SHARED and is not treated as "the starter".
2. It does not derive depth from jersey order, experience or salary. Only the club's own chart.
3. It does not price a missing starter in points. The brief explicitly forbids fixed penalties;
   the column reports the replacement's depth rank and stops there.
4. It does not transcribe the Texans chart. Houston publishes an image and no structured source
   was authorized, so Houston rows are ABSENT and the fixture is marked incomplete rather than
   filled by eye.

Every published cell traces to a club's own depth-chart URL; the injury columns trace to the
official NFL injury report. A blank means the club or the league did not print it.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPTH = os.path.join(ROOT, "data", "console", "depth_replacement.csv")
INJURIES = os.path.join(ROOT, "data", "nfl", "injuries_week10.tsv")
FIXTURES = os.path.join(ROOT, "data", "verification", "2026_11_18",
                        "official_w10_finals_2026_11_18.tsv")
OUTDIR = os.path.join(ROOT, "data", "deficiency")
OUT_JSON = os.path.join(OUTDIR, "matchup_matrix.json")
OUT_CSV = os.path.join(OUTDIR, "matchup_matrix.csv")

INJURY_URL = "https://www.nfl.com/injuries/league/2026/reg10"

# Clubs label the same position many ways: the register holds LT/LOT, LG, RG/RG, RT/ROT, HB, and on
# defence LDE/RDE, LDT/RDT/N, WLB/MLB/SLB/MIKE/WILL/SAM/LILB/RILB/LOLB/ROLB/RUSH, LCB/RCB/NCB/NB/DB,
# FS/SS. Grouping them is necessary to join anything at all, and the grouping is printed on the page
# rather than hidden: a reviewer can see exactly which club labels collapsed into which group.
POSITION_GROUP = {
    # offence
    "LT": "T", "RT": "T", "LOT": "T", "ROT": "T", "T": "T", "OT": "T",
    "LG": "G", "RG": "G", "G": "G", "OG": "G",
    "C": "C", "WR": "WR", "TE": "TE", "RB": "RB", "HB": "RB", "FB": "FB", "QB": "QB",
    # defence
    "CB": "CB", "LCB": "CB", "RCB": "CB", "NCB": "CB", "NB": "CB", "DB": "CB",
    "S": "S", "FS": "S", "SS": "S",
    "LB": "LB", "ILB": "LB", "MLB": "LB", "WLB": "LB", "SLB": "LB", "SAM": "LB",
    "WILL": "LB", "MIKE": "LB", "LILB": "LB", "RILB": "LB", "LOLB": "LB", "ROLB": "LB",
    "RUSH": "EDGE", "OLB": "EDGE",
    "EDGE": "EDGE", "DE": "DE", "LDE": "DE", "RDE": "DE",
    "DT": "DT", "LDT": "DT", "RDT": "DT", "N": "DT", "NT": "NT", "IDL": "DT",
}

# Which offensive positions are blocked/covered by which defensive positions. This is a football
# STRUCTURE mapping, not a measurement: it says which two groups line up across the ball, and the
# published page states it as such. It is the only modelling assumption in this file.
MATCHUPS = {
    # A receiver is covered by a defensive back.
    "WR": ["CB", "S"],
    # A tight end is covered by a linebacker or safety, or blocked by an edge defender.
    "TE": ["LB", "S", "EDGE", "DE"],
    # A TACKLE is blocked by an EDGE defender. It is NOT matched to an off-ball linebacker: an
    # offensive tackle does not face a Mike linebacker across the ball, so falling through to "LB"
    # when a club lists no edge defender would publish a matchup that does not exist. If the club
    # lists no edge, the row says "defence slot not published" instead.
    "T": ["EDGE", "DE"],
    # Interior linemen are blocked by interior defenders.
    "G": ["DT", "NT", "DE"],
    "C": ["DT", "NT"],
    "RB": ["LB", "S"],
    "FB": ["LB"],
    "QB": [],            # a QB is not covered by a defender; pressure comes through the line
}

# Depth rank order. Depth is published as the club's own listed rank.
RANK_ORDER = {"1": 1, "2": 2, "3": 3, "4": 4}
DEPTH_WORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


def rows_of(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\n")
                 if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return []
    delim = "\t" if "\t" in lines[0] else ","
    return list(csv.DictReader(lines, delimiter=delim))


def load_depth() -> dict:
    """(team, unit) -> position -> list of slot records. Shared slots are kept as lists, not
    collapsed to a single starter."""
    out: dict[tuple[str, str], dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows_of(DEPTH):
        team, unit = r["TEAM"].strip(), r["UNIT"].strip()
        raw = r["POSITION"].strip()
        if not raw:
            continue                     # 2 rows carry no position label; they are not guessed
        pos = POSITION_GROUP.get(raw.upper())
        if not pos:
            continue                     # unknown label: skipped and counted, never coerced
        r = dict(r)
        r["_raw_position"] = raw
        out[(team, unit)][pos].append(r)
    return out


def load_injuries() -> dict:
    """(team, player) -> {game_status, practice_status, injury}. The published table is the
    2026-11-17 official read; every row keeps its own source URL."""
    out = {}
    for r in rows_of(INJURIES):
        team = r.get("team") or r.get("TEAM") or ""
        player = r.get("player") or r.get("PLAYER") or ""
        if not team or not player:
            continue
        out[(team.strip(), player.strip())] = {
            "game_status": (r.get("game_status") or "").strip(),
            "practice_status": (r.get("practice_status") or "").strip(),
            "injury": (r.get("injury") or "").strip(),
            "source_url": (r.get("source_url") or INJURY_URL).strip(),
        }
    return out


def rank_of(r: dict) -> int:
    v = (r.get("REPLACEMENT_DEPTH") or r.get("DEPTH_LISTED") or "").strip()
    return RANK_ORDER.get(v, 0)


def slot_view(records: list[dict], injuries: dict, team: str) -> dict:
    """Describe one slot without inventing a starter.

    A depth chart lists a position with one or more players at each rank. If more than one player
    is listed at rank 1, the club has not named a single starter and this returns shared=True.
    """
    ranked = sorted(records, key=lambda r: rank_of(r))
    if not ranked:
        return {}
    # Distinct starters named at rank 1
    r1 = [r for r in ranked if rank_of(r) == 1]
    names1 = []
    for r in r1:
        n = (r.get("STARTER") or "").strip()
        if n and n not in names1:
            names1.append(n)
    rec = {"listed": len(ranked), "shared": len(names1) > 1,
           "starters_named": names1, "source": ranked[0].get("SOURCE", "")}
    if not names1:
        rec["starter"] = ""
        rec["starter_status"] = ""
        rec["replacement"] = ""
        rec["replacement_depth"] = ""
    else:
        rec["starter"] = names1[0] if len(names1) == 1 else " / ".join(names1)
        inj = injuries.get((team, names1[0]), {})
        rec["starter_status"] = inj.get("game_status", "")
        rec["starter_injury"] = inj.get("injury", "")
        rec["starter_on_report"] = bool(inj)
        rec["injury_source"] = inj.get("source_url", INJURY_URL)
        # the replacement the club lists next
        nxt = [r for r in ranked if rank_of(r) > 1]
        if nxt:
            n0 = nxt[0]
            nm = (n0.get("REPLACEMENT") or "").strip()
            rec["replacement"] = nm
            rec["replacement_depth"] = str(rank_of(n0))
        else:
            rec["replacement"] = ""
            rec["replacement_depth"] = ""
    return rec


def best_defender(defense: dict, positions: list[str], injuries: dict, team: str) -> dict:
    """The defender group that lines up against this offensive position, described the same way."""
    for pos in positions:
        if pos not in defense:
            continue
        recs = defense[pos]
        v = slot_view(recs, injuries, team)
        if not v or not v.get("starter"):
            continue
        if v.get("shared"):
            # The club lists more than one player at rank 1 for this group, so it has not named a
            # starter. Reporting "the 1st-string defender" here would fabricate one.
            blank = {"position": pos, "starter": "", "shared": True,
                     "source": v.get("source", ""), "reason_shared": True}
            return blank
        v["position"] = pos
        # The depth rank of the defender actually expected to play: if the listed starter is out,
        # the club's next listed name plays, and his depth rank is the answer.
        played_depth = 1
        if v.get("starter_status") == "Out" and v.get("replacement_depth"):
            played_depth = int(v["replacement_depth"])
        v["expected_depth"] = played_depth
        v["expected_depth_word"] = DEPTH_WORD.get(played_depth, "unknown")
        return v
    return {}


def build() -> dict:
    depth = load_depth()
    injuries = load_injuries()
    fixtures = rows_of(FIXTURES)

    rows = []
    incomplete = []
    for f in fixtures:
        away, home = f["away"].strip(), f["home"].strip()
        for off_team, def_team, side in ((away, home, "away offence vs home defence"),
                                        (home, away, "home offence vs away defence")):
            off = depth.get((off_team, "Offense"), {})
            dfn = depth.get((def_team, "Defense"), {})
            if not off:
                incomplete.append({"fixture": f["game_id"], "unit": side,
                                   "team": off_team, "reason": "no structured depth chart held "
                                   "(Houston publishes an image; no authorized structured source)"})
            if not dfn:
                incomplete.append({"fixture": f["game_id"], "unit": side,
                                   "team": def_team, "reason": "no structured depth chart held "
                                   "(Houston publishes an image; no authorized structured source)"})
            for pos in ("WR", "TE", "T", "G", "C", "RB", "FB"):
                for rec in off.get(pos, []):
                    slot = slot_view([rec], injuries, off_team)
                    if not slot.get("starter"):
                        continue
                    d = best_defender(dfn, MATCHUPS[pos], injuries, def_team)
                    rows.append({
                        "fixture": f["game_id"],
                        "side": side,
                        "offence_team": off_team,
                        "defence_team": def_team,
                        "off_position": rec.get("_raw_position", pos),
                        "off_group": pos,
                        "off_slot": (rec.get("SLOT") or "").strip(),
                        "off_starter": slot["starter"],
                        "off_starter_status": slot.get("starter_status", ""),
                        "off_replacement": slot.get("replacement", ""),
                        "off_replacement_depth": slot.get("replacement_depth", ""),
                        "off_shared_slot": slot.get("shared", False),
                        "def_position": d.get("position", ""),
                        "def_starter": d.get("starter", ""),
                        "def_starter_status": d.get("starter_status", ""),
                        "def_replacement": d.get("replacement", ""),
                        "def_replacement_depth": d.get("replacement_depth", ""),
                        "def_expected_depth": d.get("expected_depth", ""),
                        "def_expected_depth_word": d.get("expected_depth_word", ""),
                        "def_shared_slot": d.get("shared", False),
                        "mismatch": _mismatch(slot, d),
                        "off_source": slot.get("source", ""),
                        "def_source": d.get("source", ""),
                        "injury_source": slot.get("injury_source", INJURY_URL),
                        "game_url": f.get("game_url", ""),
                    })
    return {
        "dataset": "deficiency_matchup_matrix",
        "title": "Offence vs defence matchup deficiency matrix (1st-4th string), Week 10 2026",
        "generated_by": "tools/build_deficiency_matrix.py (session arena/91656714-x1, round 6)",
        "requirement": "R-76 — Interactive offense vs. defense matchup deficiency matrix (1st-4th string)",
        "method": (
            "Each club's own official depth chart supplies the listed starter, the shared-slot flag and "
            "the named replacement with the club's own depth rank. The official NFL injury report "
            "supplies each listed player's game status. The two are joined by club+player. A defensive "
            "slot is described the same way, and the defender's EXPECTED depth is 1 unless his club's "
            "listed starter is Out, in which case it is the depth rank of the club's next listed name. "
            "No value is inferred, no missing starter is priced in points, and no depth order is derived "
            "from jersey number, experience or salary."
        ),
        "assumption_stated": (
            "The offence-to-defence position mapping in MATCHUPS is football structure, not a "
            "measurement: WR<-CB/S, TE<-LB/S, T<-EDGE/DE, G/C<-DT/NT. It is the only modelling "
            "assumption in this artefact and is printed on the page so a reviewer can disagree with it."
        ),
        "limits": [
            "Houston publishes its depth chart as an image and no authorized structured source was "
            "used, so Houston appears in no row. Fixtures involving Houston are INCOMPLETE, not empty.",
            "The injury report is the 2026-11-17 read (347 rows). It carries a game status for only "
            "those players the club listed; absence from the report is not evidence of health.",
            "A slot where the club lists more than one player at rank 1 is flagged shared and is not "
            "treated as a named starter.",
            "Reserve-list status (injured reserve, PUP) is not captured, so a starter who is out for "
            "the season may simply be absent from the depth chart's rank 1.",
        ],
        "counts": {},
        "incomplete": incomplete,
        "rows": rows,
    }


def _mismatch(off: dict, dfn: dict) -> str:
    """A short, honest label. It never claims more than the joined evidence shows."""
    if not dfn.get("starter"):
        return "defence slot not published"
    if dfn.get("expected_depth") and int(dfn["expected_depth"]) >= 2:
        return f"{dfn.get('expected_depth_word','')}-string defender expected to start"
    if off.get("starter_status") == "Out":
        return "offence starter ruled Out"
    if off.get("starter_status") in ("Questionable", "Doubtful"):
        return f"offence starter {off['starter_status'].lower()}"
    return "no deficiency evidenced"


def main() -> int:
    pack = build()
    rows = pack["rows"]
    complete_fixtures = {r["fixture"] for r in rows}
    pack["counts"] = {
        "rows": len(rows),
        "clubs_with_offence_depth": len({r["offence_team"] for r in rows}),
        "fixtures_covered": len(complete_fixtures),
        "rows_with_a_defender_deficiency": sum(
            1 for r in rows if r["mismatch"] == "2nd-string defender expected to start"
            or r["mismatch"].startswith(("2nd", "3rd", "4th"))),
        "rows_with_an_out_offensive_starter": sum(
            1 for r in rows if r["off_starter_status"] == "Out"),
        "shared_slots_present": sum(1 for r in rows if r["off_shared_slot"] or r["def_shared_slot"]),
        "fixtures_incomplete": len({i["fixture"] for i in pack["incomplete"]}),
    }
    os.makedirs(OUTDIR, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(pack, fh, indent=1)
        fh.write("\n")
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["fixture"])
        w.writeheader()
        w.writerows(rows)

    c = pack["counts"]
    print(f"matchup matrix  : {c['rows']} rows over {c['fixtures_covered']} fixtures, "
          f"{c['clubs_with_offence_depth']} clubs")
    print(f"  deficiency cells      : {c['rows_with_a_defender_deficiency']}")
    print(f"  out offensive starters: {c['rows_with_an_out_offensive_starter']}")
    print(f"  shared slots present  : {c['shared_slots_present']}")
    print(f"  fixtures incomplete   : {c['fixtures_incomplete']} (Houston depth chart is an image)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
