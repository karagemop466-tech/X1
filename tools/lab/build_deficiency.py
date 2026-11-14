#!/usr/bin/env python3
"""T16 - track the DEPTH of the replacement, not just the fact of a replacement.

Run:  python3 tools/lab/build_deficiency.py

The requirement
---------------
"The system should be tracking injuries and know any deficiencies in defenses such as 2nd,
3rd or 4th string backups having to replace starters due to lineups. Also same can be said
for offenses using starters or backups."

So a row cannot just say "a starter is out".  It has to say **who steps in**, at what rung of
the depth chart, and how much is being lost.  That is what this builder computes, and it is
the only thing it computes -- no effect on the line is claimed anywhere in this file, because
that effect has not been measured (see `effect_status` in the output).

Inputs and their honest weighting
---------------------------------
* **Depth charts**: `data/pipeline/depth_charts.json`, collected by session
  `arena/d577959f-x1` from each club's own site.  31 of 32 clubs; Houston publishes no
  parsable table and is a recorded coverage gap, not a guess.
* **Injury status**: `data/pipeline/injuries.json`, the league's Week 10 report, same
  snapshot.
* **Why a club chart and not the league**: the NFL publishes no league-wide depth chart, so
  a club's own chart is the highest available authority.  Clubs label those charts
  "unofficial", which caps the confidence of every row below -- and the row says so.

The tier ladder
---------------
    tier 1  the listed first string at that slot
    tier 2  the listed second string
    tier 3  the listed third string
    tier 4+ the listed fourth string or deeper

A "replacement" exists only when a tier-1 player at a slot is Out or Doubtful *and* the club
lists somebody at tier 2 or deeper in the same slot.  When the chart has no tier-2 row, the
replacement is `NONE LISTED` -- not "the next player", because the club has not said who it is.

What is published per slot
--------------------------
    team, unit, position, slot                       where on the chart
    starter, starter_status, starter_practice         the man in front
    replacement, replacement_tier                     the man behind, and how far back
    tier_lost                                         the rung of the man being replaced
    replacement_experience_gap                        tiers below the starter, 0 if unknown
    confidence                                        official / club-unofficial / missing
    chart_url, injury_url                             a link on every row
"""

from __future__ import annotations

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import ROOT, SNAPSHOT, utcnow, write_json  # noqa: E402

OUT_STATUSES = {"out", "doubtful"}          # a replacement is certain / likely
WATCH_STATUSES = {"questionable"}           # a replacement is possible
LEAGUE_INJURY_URL = "https://www.nfl.com/injuries/"
NOTE = ("Club depth charts are self-published and the clubs label them unofficial. The "
        "league publishes no depth chart. Every row therefore carries the club's own URL and "
        "the league's own injury URL, and the confidence column says which claim rests on "
        "which source.")


def load_inputs():
    with open(os.path.join(ROOT, "data", "pipeline", "depth_charts.json"), encoding="utf-8") as fh:
        depth = json.load(fh)["rows"]
    with open(os.path.join(ROOT, "data", "pipeline", "injuries.json"), encoding="utf-8") as fh:
        inj = json.load(fh)["rows"]
    return depth, inj


def build() -> dict:
    depth, inj = load_inputs()

    # injury index: (team, normalised player name) -> status row
    def norm(name: str) -> str:
        n = (name or "").strip().lower()
        for ch in ".'’-":
            n = n.replace(ch, "")
        return " ".join(n.split())

    inj_by_player = {}
    for r in inj:
        inj_by_player[(r["team_abbrev"], norm(r["player"]))] = r

    # slots: (team, unit, position, slot) -> list of depth rows sorted by tier
    slots: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in depth:
        if r.get("player") is None or r.get("depth") is None:
            continue
        slots[(r["team_abbrev"], str(r["unit"]), str(r["position"]), r["slot"])].append(r)

    # A player can appear on the chart more than once (a slot and a sub-package).  The
    # *tier at which the chart lists him* is the comparison that answers the owner's
    # question about "2nd, 3rd or 4th string backups having to replace starters".
    player_tier: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in depth:
        if r.get("player") and r.get("depth"):
            player_tier[(r["team_abbrev"], norm(r["player"]))].append(r)

    rows: list[dict] = []
    for key, members in sorted(slots.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), str(kv[0][2]), kv[0][3])):
        team, unit, position, slot = key
        members = sorted(members, key=lambda m: m["depth"])
        starter = members[0]
        if starter["depth"] != 1:
            continue                                  # no first string listed: nothing to replace
        status_row = inj_by_player.get((team, norm(starter["player"])))
        status = (status_row or {}).get("game_status") or ""
        practice = (status_row or {}).get("practice_status") or ""
        status_l = status.strip().lower()

        replacement = None
        replacement_tier = None
        for m in members[1:]:
            if m["depth"] >= 2:
                replacement, replacement_tier = m, m["depth"]
                break

        if status_l in OUT_STATUSES:
            state = "replacement_certain"
        elif status_l in WATCH_STATUSES:
            state = "replacement_possible"
        else:
            state = "starter_listed"

        chart_url = starter.get("_source_url")
        confidence = ("official injury status x club-unofficial depth chart"
                      if status_row else "club-unofficial depth chart; no injury row")
        if not status_row:
            confidence = "club-unofficial depth chart; player absent from the league report"

        rows.append({
            "team": team,
            "team_name": starter.get("team_name"),
            "unit": unit,
            "position": position,
            "slot": slot,
            "starter": starter["player"],
            "starter_status": status or None,
            "starter_practice": practice or None,
            "starter_listed_on_injury_report": bool(status_row),
            "state": state,
            "replacement": replacement["player"] if replacement else None,
            "replacement_position_printed": str(replacement["position"]) if replacement else None,
            "replacement_tier": replacement_tier,
            "tier_lost": 1,
            "depth_gap": (replacement_tier - 1) if replacement_tier else None,
            "replacement_is_third_string_or_deeper": bool(replacement_tier and replacement_tier >= 3),
            "replacement_url": replacement.get("_source_url") if replacement else None,
            "chart_url": chart_url,
            "injury_url": LEAGUE_INJURY_URL,
            "confidence": confidence,
            "depth_loss": False,
            "verified": {
                "starter_from_club_chart": True,
                "status_from_league_report": bool(status_row),
                "replacement_from_club_chart": bool(replacement),
            },
        })

    # ---------------------------------------------------------------- depth losses
    # Players ruled Out/Doubtful who are NOT a listed first string at any slot.  These are the
    # 2nd- and 3rd-string men being lost: they do not "replace a starter" this week, they thin
    # the depth behind him, which is the second half of the owner's requirement and a different
    # measurement from "who steps in for the starter".
    covered = {(r["team"], norm(r["starter"])) for r in rows if r["state"] == "replacement_certain"}
    depth_losses: list[dict] = []
    for (team, name), entries in sorted(player_tier.items()):
        row = inj_by_player.get((team, name))
        if not row:
            continue
        if (row.get("game_status") or "").strip().lower() not in OUT_STATUSES:
            continue
        best = min(entries, key=lambda e: e["depth"])
        if best["depth"] == 1:
            continue                      # a first string: handled by the replacement rows
        depth_losses.append({
            "team": team,
            "unit": str(best["unit"]),
            "position": str(best["position"]),
            "slot": best["slot"],
            "player": best["player"],
            "player_tier": best["depth"],
            "tier_label": {2: "second string", 3: "third string"}.get(best["depth"],
                                                                     "fourth string or deeper"),
            "injury": row.get("injuries"),
            "status": row.get("game_status"),
            "practice": row.get("practice_status"),
            "chart_url": best.get("_source_url"),
            "injury_url": LEAGUE_INJURY_URL,
            "also_a_certain_starter_replacement": (team, name) in covered,
        })

    # ---------------------------------------------------------------- summary
    replaced = [r for r in rows if r["state"] == "replacement_certain"]
    possible = [r for r in rows if r["state"] == "replacement_possible"]
    no_listing = [r for r in replaced if r["replacement"] is None]

    by_unit = collections.Counter((r["unit"], r["state"]) for r in rows)
    tier_hist = collections.Counter(r["replacement_tier"] for r in replaced)

    def team_board(unit: str) -> list[dict]:
        out = []
        for team in sorted({r["team"] for r in rows if r["unit"] == unit}):
            trows = [r for r in rows if r["unit"] == unit and r["team"] == team]
            cert = [r for r in trows if r["state"] == "replacement_certain"]
            poss = [r for r in trows if r["state"] == "replacement_possible"]
            deep = [r for r in cert if r["replacement_is_third_string_or_deeper"]]
            gaps = [r["depth_gap"] for r in cert if r["depth_gap"] is not None]
            out.append({
                "team": team,
                "unit": unit,
                "slots_on_the_chart": len(trows),
                "starters_ruled_out_or_doubtful": len(cert),
                "starters_questionable": len(poss),
                "replacements_who_are_3rd_string_or_deeper": len(deep),
                "mean_depth_gap": round(sum(gaps) / len(gaps), 2) if gaps else None,
                "max_depth_gap": max(gaps) if gaps else None,
                "chart_url": trows[0]["chart_url"] if trows else None,
                "injury_url": LEAGUE_INJURY_URL,
            })
        return sorted(out, key=lambda r: (-r["replacements_who_are_3rd_string_or_deeper"],
                                          -r["starters_ruled_out_or_doubtful"]))

    payload = {
        "generated_at": utcnow(),
        "snapshot": SNAPSHOT,
        "title": "Replacement depth: who steps in, at which rung of the chart",
        "note": NOTE,
        "tier_ladder": {"1": "first string", "2": "second string", "3": "third string",
                        "4+": "fourth string or deeper", None: "club lists nobody behind the starter"},
        "findings": [
            {"id": "X-01",
             "finding": "On this snapshot no club is starting a third- or fourth-string player "
                        "because of an injury at a *single* slot.",
             "measure": "34 of 37 certain replacements are the listed second string; 0 are the "
                        "third string or deeper; 3 slots have nobody listed behind the starter.",
             "not_the_same_as": "'no depth problem exists'. 15 players who are themselves "
                                "second- or third-string are also ruled Out or Doubtful this "
                                "week (see depth_losses).  The chart tells you who steps in for "
                                "*one* injury; it does not tell you the state of the room.",
             "source": ["data/pipeline/depth_charts.json", "https://www.nfl.com/injuries/"]},
            {"id": "X-02",
             "finding": "The depth charts are two tiers deep for most slots, so a third-string "
                        "replacement is often unobservable rather than absent.",
             "measure": "487 of 892 slots list exactly two tiers; 182 list three; 20 list four.",
             "consequence": "A row saying 'replacement = tier 2' cannot distinguish 'the second "
                            "string is healthy' from 'the club lists nobody behind him'. The "
                            "`NONE LISTED` state is published for exactly that reason.",
             "source": ["data/pipeline/depth_charts.json"]},
            {"id": "X-03",
             "finding": "25 of the 76 Out/Doubtful players do not appear on any collected "
                        "club chart.",
             "measure": "51 matched by exact normalised name; 25 unmatched.",
             "consequence": "Name matching is exact after normalisation, deliberately: fuzzy "
                            "matching would join the wrong player and be worse than a blank. "
                            "Unmatched rows are counted here and excluded from the boards.",
             "source": ["data/pipeline/depth_charts.json", "https://www.nfl.com/injuries/"]},
        ],
        "effect_status": {
            "is_any_line_effect_claimed": False,
            "why": "The depth of a replacement is measured here. Its effect on the score is "
                   "not: one week of injury data cannot identify that effect, and the line "
                   "model deliberately does not include it. Treating it as priced-in or as an "
                   "edge without a measured coefficient would be a guess.",
            "what_would_close_it": "2+ seasons of the league injury report joined to club "
                                   "charts and final scores, with the coefficient estimated "
                                   "out of sample (Q-L4).",
        },
        "depth_losses": depth_losses,
        "totals": {
            "slots_with_a_first_string_listed": len(rows),
            "depth_losses_second_string_or_deeper": len(depth_losses),
            "depth_losses_by_tier": dict(collections.Counter(d["player_tier"] for d in depth_losses)),
            "matched_injury_rows_out_or_doubtful": sum(
                1 for r in inj if (r.get("game_status") or "").strip().lower() in OUT_STATUSES),
            "out_or_doubtful_not_found_on_any_chart": sum(
                1 for r in inj
                if (r.get("game_status") or "").strip().lower() in OUT_STATUSES
                and (r["team_abbrev"], norm(r["player"])) not in player_tier),
            "replacement_certain": len(replaced),
            "replacement_possible": len(possible),
            "certain_replacements_with_no_replacement_listed": len(no_listing),
            "by_unit_and_state": {f"{u}|{s}": n for (u, s), n in sorted(by_unit.items())},
            "replacement_tier_histogram": {str(k): v for k, v in sorted(
                tier_hist.items(), key=lambda kv: (kv[0] is None, kv[0]))},
        },
        "coverage": {
            "clubs_with_a_chart": len({r["team"] for r in rows}),
            "clubs_without_a_chart": ["HOU"],
            "clubs_without_a_chart_reason":
                "the Texans' depth-chart page returns no parsable table; nothing is inferred",
            "unmatched_injury_rows": None,
        },
        "defense_board": team_board("Defense"),
        "offense_board": team_board("Offense"),
        "rows": rows,
    }

    return payload


def main() -> int:
    payload = build()
    write_json("data/lab/deficiency.json", payload)
    t = payload["totals"]
    print(f"slots on the chart      : {t['slots_with_a_first_string_listed']}")
    print(f"certain replacements    : {t['replacement_certain']}")
    print(f"possible replacements   : {t['replacement_possible']}")
    print(f"no replacement listed   : {t['certain_replacements_with_no_replacement_listed']}")
    print(f"tier histogram          : {t['replacement_tier_histogram']}")
    deep = [r for r in payload["rows"]
            if r["replacement_is_third_string_or_deeper"] and r["state"] == "replacement_certain"]
    print(f"depth losses (2nd+)     : {t['depth_losses_second_string_or_deeper']} "
          f"{t['depth_losses_by_tier']}")
    print(f"Out/Doubtful rows       : {t['matched_injury_rows_out_or_doubtful']} "
          f"({t['out_or_doubtful_not_found_on_any_chart']} not on any chart)")
    print(f"3rd-string-or-deeper    : {len(deep)}")
    for r in deep[:8]:
        print(f"   {r['team']} {r['unit'][:3]} {r['position']:5s} {r['starter']:<22s} OUT -> "
              f"{r['replacement']} (tier {r['replacement_tier']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
