#!/usr/bin/env python3
"""Turn the retained injury captures into a published, timestamped *delta* series.

    python3 tools/build_availability_series.py            # write the store
    python3 tools/build_availability_series.py --check    # fail if the committed files are stale

Why this file exists
--------------------
The brief asks for four things that the repository had pieces of but never joined:

  "Store every injury-hub read with its clock time and publish the delta, never the level"
  "Make the injury signal a surprise, never a level"
  "Treat the injury report as a timestamped series, not a weekly snapshot"
  "Publish a weekly 'what changed' diff instead of a static snapshot"

`data/captures/index.jsonl` already holds every read the collector made, each with a UTC clock
time and a content hash, and the retained payload JSON gives the rows as they were known. What was
missing is the *join* between consecutive reads and the published delta. That is all this builder
does: it reads, it joins, it counts. It never writes to the capture store.

Two rules this builder enforces by construction
-----------------------------------------------
1. **The delta is the product.** Every state row carries its change against the previous state
   first; the level (counts of Out/Questionable/...) is published beside it as context, not as the
   headline. A state with no previous state says "anchor", not "0 changes".
2. **A join is never silent.** The club code for the Rams appears as both `LA` and `LAR` across
   captures, and the collector's `game_label` field changed format between reads (day header vs
   matchup). Joining on the raw values reports 14 players "departed" and 14 "arrived" who are the
   same 14 rows. Both the phantom number and the normalised number are published, side by side, so
   the reader can see exactly what the alias is worth. The alias table is an output, not a secret.

Nothing here is a claim about the league's rules: the designation ordering used to call a change an
upgrade or a downgrade is *this project's* definition, and it is printed on the page it feeds.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
IDX = os.path.join(D, "captures", "index.jsonl")
OUT = os.path.join(D, "availability_series")

DATASET = "injuries"

# Join aliases only. Payloads are never rewritten: `capture_store` keeps what each source printed,
# and the same split is already recorded in data/captures/config.json ("diff_alias").
CLUB_ALIAS = {"LAR": "LA", "ARZ": "AZ"}

# This project's severity ordering, published with the page it feeds.
GAME_STATUS_ORDER = {"": 0, "Questionable": 1, "Doubtful": 2, "Out": 3}
PRACTICE_ORDER = {"Full Participation in Practice": 0, "Limited Participation in Practice": 1,
                  "Did Not Participate In Practice": 2, "": -1}
CHANGE_FIELDS = ("game_status", "practice_status", "injury", "position")

ET_OFFSET_H = 5          # November in the US: EST = UTC-5 (no DST change before March 2026)
SURPRISE_WINDOW_H = 24.0  # our own definition, printed on the page


# --------------------------------------------------------------------------- io
def _read_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def _utc(stamp: str) -> dt.datetime:
    """The store writes both '...Z' and '...+00:00'. Both mean one instant."""
    s = (stamp or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def _name(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _content_sha(rows) -> str:
    """Same definition pipeline/capture_store.py uses: sha256 over json.dumps(rows, sort_keys)."""
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode("utf-8")).hexdigest()


def _rows_of(entry) -> list[dict]:
    payload_path = os.path.join(ROOT, entry["payload"])
    with open(payload_path, encoding="utf-8") as fh:
        p = json.load(fh)
    return p["rows"] if isinstance(p, dict) else p


def _method(entry) -> str:
    note = (entry.get("note") or "").lower()
    if "transcription" in note:
        return "hand transcription"
    return "collector"


# --------------------------------------------------------------------------- fixtures
def club_fixture_map() -> dict:
    """club -> (game_id, kickoff UTC) for the 2026 Week 10 slate.

    Dates come from the Week 10 finals (verified official read, data/console/w10_finals_2026_11_17.csv)
    and the printed kickoff slot from the published schedule table (data/console/schedule_week10.csv,
    KICKOFF_ET). Both are already in the repository and already verified elsewhere; nothing here
    re-reads a page.
    """
    sched = {}
    with open(os.path.join(D, "console", "schedule_week10.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sched[r["GAMEID"].replace("-2026-reg-10", "")] = r
    out = {}
    path = os.path.join(D, "console", "w10_finals_2026_11_17.csv")
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            slug = r["game_url"].rstrip("/").split("/")[-1]
            key = slug.replace("-2026-reg-10", "")
            s = sched.get(key, {})
            ko_et = (s.get("KICKOFF_ET") or "").strip()
            date = (r.get("date_et") or "").strip()
            kickoff = None
            if date and ko_et:
                # strptime handles the meridiem, so 1:00 PM is 13:00 and 8:15 PM is 20:15.
                t = dt.datetime.strptime(ko_et.replace(" ", ""), "%I:%M%p")
                d0 = dt.datetime.strptime(date, "%Y-%m-%d")
                naive = d0.replace(hour=t.hour, minute=t.minute)
                # ET -> UTC in November (EST, no DST in force): +5 h
                kickoff = (naive + dt.timedelta(hours=ET_OFFSET_H)).replace(tzinfo=dt.timezone.utc)
            for club in (r["away"], r["home"]):
                out[CLUB_ALIAS.get(club, club)] = dict(game_id=r["game_id"],
                                                        matchup=f'{r["away"]} at {r["home"]}',
                                                        kickoff_utc=kickoff,
                                                        kickoff_et=ko_et,
                                                        date_et=date)
    return out


# --------------------------------------------------------------------------- diff
def _key(row) -> tuple:
    return (CLUB_ALIAS.get(row.get("team", ""), row.get("team", "")), row.get("player", ""))


def _key_raw(row) -> tuple:
    return (row.get("team", ""), row.get("player", ""))


def index_rows(rows):
    out = {}
    dupes = []
    for r in rows:
        k = _key(r)
        if k in out:
            dupes.append(k)
        out[k] = r
    return out, dupes


def diff(prev_rows, next_rows):
    a, a_dup = index_rows(prev_rows)
    b, b_dup = index_rows(next_rows)
    added = [b[k] for k in sorted(set(b) - set(a))]
    removed = [a[k] for k in sorted(set(a) - set(b))]
    changes = []
    for k in sorted(set(a) & set(b)):
        for f in CHANGE_FIELDS:
            x, y = a[k].get(f, "") or "", b[k].get(f, "") or ""
            if x != y:
                changes.append(dict(team=k[0], player=k[1], field=f, from_value=x, to_value=y,
                                    game_label_from=a[k].get("game_label", ""),
                                    game_label_to=b[k].get("game_label", ""),
                                    position=b[k].get("position", "")))
    # the same diff without alias normalisation, to price the alias
    ar = {_key_raw(r): r for r in prev_rows}
    br = {_key_raw(r): r for r in next_rows}
    phantom = dict(added=len(set(br) - set(ar)), removed=len(set(ar) - set(br)))
    return dict(added=added, removed=removed, changes=changes,
                n_shared=len(set(a) & set(b)), dupes=len(a_dup) + len(b_dup),
                phantom=phantom)


def direction(field, frm, to):
    if field == "game_status":
        o = GAME_STATUS_ORDER
    elif field == "practice_status":
        o = PRACTICE_ORDER
    else:
        return "descriptive"
    a, b = o.get(frm, None), o.get(to, None)
    if a is None or b is None:
        return "unranked"
    if b > a:
        return "downgrade"
    if b < a:
        return "upgrade"
    return "same"


def counts(rows):
    """Levels, for context beside the delta. Never published on their own."""
    c = dict(rows=len(rows), out=0, doubtful=0, questionable=0, game_status_blank=0,
             dnp=0, lp=0, fp=0, practice_other=0)
    gs_map = {"Out": "out", "Doubtful": "doubtful", "Questionable": "questionable"}
    ps_map = {"Did Not Participate In Practice": "dnp",
              "Limited Participation in Practice": "lp",
              "Full Participation in Practice": "fp"}
    clubs = set()
    for r in rows:
        clubs.add(CLUB_ALIAS.get(r.get("team", ""), r.get("team", "")))
        c[gs_map.get(r.get("game_status") or "", "game_status_blank")] += 1
        c[ps_map.get(r.get("practice_status") or "", "practice_other")] += 1
    c["clubs"] = len(clubs)
    return c


# --------------------------------------------------------------------------- build
def build():
    entries = [e for e in _read_jsonl(IDX) if e.get("dataset") == DATASET]
    entries.sort(key=lambda e: _utc(e["as_read_at"]))
    fixtures = club_fixture_map()

    captures, states, changes_all, movement = [], [], [], {}
    prev_state = None
    seen_hash = {}
    for e in entries:
        rows = _rows_of(e)
        sha = e["content_sha256"]
        first = sha not in seen_hash
        if first:
            seen_hash[sha] = len(states) + 1
        state_id = f"S{seen_hash[sha]}"
        read_at = _utc(e["as_read_at"])
        c = counts(rows)
        captures.append(dict(
            capture_id=e["capture_id"], as_read_at=e["as_read_at"], read_utc=_name(read_at),
            method=_method(e), state_id=state_id,
            content_sha256=sha, content_sha_recomputed=_content_sha(rows),
            payload_file=e["payload"], payload_sha256_file=_sha_file(os.path.join(ROOT, e["payload"])),
            prev_content_sha256=e.get("prev_content_sha256", ""),
            drift=e.get("drift", ""), drift_violations=len(e.get("drift_violations") or []),
            sources=" ".join(e.get("sources") or []), note=e.get("note", ""),
            **{k: v for k, v in c.items() if k != "rows"},
        ))
        if first:
            st = dict(state_id=state_id, first_read_utc=_name(read_at), last_read_utc=_name(read_at),
                      n_reads=1, first_capture_id=e["capture_id"], last_capture_id=e["capture_id"],
                      content_sha256=sha, methods=_method(e), **c)
            if prev_state is not None:
                prev_rows = prev_state["rows_raw"]
                d = diff(prev_rows, rows)
                pair = f'{prev_state["state_id"]}\u2192{state_id}'
                st["delta_vs_prev_state"] = (f'+{len(d["added"])} on report, '
                                             f'-{len(d["removed"])} off report, '
                                             f'{len(d["changes"])} cell changes '
                                             f'(of {d["n_shared"]} players on both reads)')
                st["phantom_added_if_joined_on_raw_team"] = d["phantom"]["added"]
                st["phantom_removed_if_joined_on_raw_team"] = d["phantom"]["removed"]
                st["prior_state"] = prev_state["state_id"]
                st["pair_method"] = (prev_state["method"] + " \u2192 " + _method(e)
                                     if prev_state["method"] != _method(e) else _method(e))
                st["hours_between_reads"] = round(
                    (read_at - prev_state["read_at"]).total_seconds() / 3600, 2)
                # per change: attach the club's kickoff so "surprise" is measurable
                for ch in d["changes"]:
                    fx = fixtures.get(ch["team"], {})
                    ko = fx.get("kickoff_utc")
                    h = round((ko - read_at).total_seconds() / 3600, 2) if ko else None
                    ch.update(pair=pair, read_utc=_name(read_at),
                              club_matchup=fx.get("matchup", ""),
                              kickoff_utc=_name(ko) if ko else "",
                              hours_to_kickoff=h,
                              direction=direction(ch["field"], ch["from_value"], ch["to_value"]),
                              in_surprise_window=("yes" if h is not None and 0 < h <= SURPRISE_WINDOW_H
                                                   else ("no" if h is not None else "unknown")))
                    changes_all.append(ch)
                    key = (pair, fx.get("matchup", "unmapped"))
                    m = movement.setdefault(key, dict(pair=pair, matchup=fx.get("matchup", "unmapped"),
                                                       kickoff_utc=_name(ko) if ko else "",
                                                       later_read_utc=_name(read_at),
                                                       hours_to_kickoff=h, cell_changes=0,
                                                       players_added=len(d["added"]),
                                                       players_removed=len(d["removed"]),
                                                       downgrades=0, upgrades=0))
                    m["cell_changes"] += 1
                    if ch["direction"] == "downgrade":
                        m["downgrades"] += 1
                    elif ch["direction"] == "upgrade":
                        m["upgrades"] += 1
                # arrivals/departures are attributed to the club's fixture too
                for tag, lst in (("players_added", d["added"]), ("players_removed", d["removed"])):
                    per = {}
                    for r in lst:
                        per[r.get("team", "")] = per.get(r.get("team", ""), 0) + 1
                    st[tag] = json.dumps(per, sort_keys=True)
            else:
                st["delta_vs_prev_state"] = "anchor: first retained read of this report; no prior state to diff"
                st["phantom_added_if_joined_on_raw_team"] = ""
                st["phantom_removed_if_joined_on_raw_team"] = ""
                st["prior_state"] = ""
                st["pair_method"] = _method(e)
                st["hours_between_reads"] = ""
            states.append(dict(st, rows_raw=rows, read_at=read_at, method=_method(e)))
        else:
            for st in states:
                if st["state_id"] == state_id and st.get("n_reads") is not None:
                    st["n_reads"] += 1
                    st["last_read_utc"] = _name(read_at)
                    st["last_capture_id"] = e["capture_id"]
                    if _method(e) not in st["methods"]:
                        st["methods"] += " + " + _method(e)
                    break
        prev_state = dict(state_id=state_id, rows_raw=rows, read_at=read_at,
                          method=_method(e), n=len(rows))

    for st in states:
        st.pop("rows_raw", None)
        st.pop("read_at", None)
        st.pop("method", None)
        st.setdefault("players_added", "")
        st.setdefault("players_removed", "")

    surprise = [c for c in changes_all if c["in_surprise_window"] == "yes"
                and c["direction"] == "downgrade"]
    by_field = {}
    for c in changes_all:
        by_field[c["field"]] = by_field.get(c["field"], 0) + 1
    by_team = {}
    for c in changes_all:
        by_team[c["team"]] = by_team.get(c["team"], 0) + 1

    summary = dict(
        dataset="availability_series",
        title="Injury-report reads as a timestamped series, with the delta published, not the level",
        generated_by="tools/build_availability_series.py",
        rule=("Every row is recomputed from the retained capture payloads. The hash in each row is "
              "the capture store's own content hash, re-derived from the payload file; a payload that "
              "no longer reproduces its published hash fails the verifier."),
        sources=dict(capture_index="data/captures/index.jsonl",
                     payloads="data/captures/payloads/injuries/",
                     store_config="data/captures/config.json",
                     official_page="https://www.nfl.com/injuries/",
                     fixture_dates=("data/console/w10_finals_2026_11_17.csv + "
                                    "data/console/schedule_week10.csv")),
        counts=dict(captures=len(captures), distinct_states=len(states),
                    clubs_in_captures=max((c["clubs"] for c in captures), default=0),
                    cell_changes=len(changes_all), changes_by_field=by_field,
                    changes_by_team=dict(sorted(by_team.items(), key=lambda kv: -kv[1])),
                    downgrades_in_surprise_window=len(surprise),
                    movement_groups=len(movement)),
        definitions=dict(
            surprise=("a downgrade (this project's ordering) recorded by a read that is within "
                      f"{SURPRISE_WINDOW_H:.0f} h of that club's kickoff"),
            game_status_order="blank < Questionable < Doubtful < Out (ours, not the league's)",
            practice_order="Full < Limited < Did Not Participate (ours)",
            alias=("join-only normalisation "
                   + ", ".join(f"{k}\u2192{v}" for k, v in sorted(CLUB_ALIAS.items()))
                   + "; payloads keep what each read printed"),
            fields_compared=", ".join(CHANGE_FIELDS),
        ),
        caveats=[
            "The three distinct states span two capture methods (collector read, hand transcription). "
            "A state pair whose methods differ is labelled as such: its delta mixes a source change "
            "with a method change and cannot be read as pure movement.",
            "Two states with identical cell contents can still carry different content hashes: the "
            "hash covers the serialised JSON, including the game_label format, not the facts alone. "
            "That is why this builder diffs cells and reports the hash next to it.",
            "The Week 11 report is not in the capture store at all: as of the 2026-11-18 probe the "
            "league page still printed Week 10 (data/verification/2026_11_18/). The series is therefore "
            "one week deep and the weekly-diff requirement stays PARTIAL until a second week exists.",
            "Kickoff times are the printed ET slots converted with a fixed EST offset (November, no DST "
            "change). The Munich fixture's printed slot is a 9:30 AM ET listing.",
        ],
        hours_surprise_window=SURPRISE_WINDOW_H,
        et_offset_h=ET_OFFSET_H,
        alias_table=[dict(from_code=k, to_code=v, why="printed spelling of the same club")
                     for k, v in sorted(CLUB_ALIAS.items())],
    )
    return captures, states, changes_all, list(movement.values()), summary


# --------------------------------------------------------------------------- write
def _csv(text_headers, rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(text_headers)
    for r in rows:
        w.writerow([r.get(h, "") for h in text_headers])
    return buf.getvalue()


CAP_COLS = ["capture_id", "read_utc", "as_read_at", "method", "state_id", "rows", "clubs",
            "out", "doubtful", "questionable", "game_status_blank", "dnp", "lp", "fp",
            "drift", "drift_violations", "content_sha256", "content_sha_recomputed",
            "payload_sha256_file", "prev_content_sha256", "payload_file", "sources", "note"]
STATE_COLS = ["state_id", "first_read_utc", "last_read_utc", "n_reads", "methods", "rows", "clubs",
              "prior_state", "pair_method", "hours_between_reads", "delta_vs_prev_state",
              "players_added", "players_removed", "phantom_added_if_joined_on_raw_team",
              "phantom_removed_if_joined_on_raw_team", "out", "doubtful", "questionable",
              "game_status_blank", "dnp", "lp", "fp", "content_sha256",
              "first_capture_id", "last_capture_id"]
CHANGE_COLS = ["pair", "read_utc", "team", "player", "position", "field", "from_value", "to_value",
               "direction", "hours_to_kickoff", "kickoff_utc", "club_matchup",
               "in_surprise_window", "game_label_from", "game_label_to"]
MOVE_COLS = ["pair", "matchup", "kickoff_utc", "later_read_utc", "hours_to_kickoff",
             "cell_changes", "downgrades", "upgrades", "players_added", "players_removed"]


def write(captures, states, changes, movement, summary, check=False):
    files = {
        "captures.csv": _csv(CAP_COLS, captures),
        "states.csv": _csv(STATE_COLS, states),
        "changes.csv": _csv(CHANGE_COLS, changes),
        "movement_by_game.csv": _csv(MOVE_COLS, movement),
        "summary.json": json.dumps(summary, indent=1) + "\n",
    }
    if check:
        bad = []
        for name, text in files.items():
            p = os.path.join(OUT, name)
            if not os.path.exists(p) or open(p, encoding="utf-8").read() != text:
                bad.append(name)
        if bad:
            print("[availability-series] STALE: " + ", ".join(bad)
                  + " - rerun python3 tools/build_availability_series.py")
            return 1
        print(f"[availability-series] current: {len(captures)} captures, {len(states)} states, "
              f"{len(changes)} cell changes")
        return 0
    os.makedirs(OUT, exist_ok=True)
    for name, text in files.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    print(f"[availability-series] wrote {len(files)} files to data/availability_series/ "
          f"({len(captures)} captures, {len(states)} distinct states, {len(changes)} changes)")
    return 0


if __name__ == "__main__":
    sys.exit(write(*build(), check="--check" in sys.argv))
