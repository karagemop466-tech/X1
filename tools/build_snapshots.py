#!/usr/bin/env python3
"""Build the PRICE-SNAPSHOT STORE (round-3 requirement S1).

Session `arena/600e6009-x1`.

What this produces
------------------
  data/snapshots/price_snapshots.json   one record per (market we originate x stage)
  data/snapshots/price_snapshots.csv    same, flat

Store contract
--------------
For EVERY market the model originates (side, total, moneyline — in that order,
see tools/build_origination.py) the store keeps two stages:

  open   the number as originated, captured before kickoff
  close  the number as published at our cut-off, captured at kickoff

Two numbers are tracked per stage:
  our_line      our own originated number        — computed, always recorded
  market_line   the market's number at that stage — blank unless an OFFICIAL
                source publishes prices (none does today: Q-02), flagged not filled

The price-data policy decision (2026-11-17, this session's N-4)
---------------------------------------------------------------
`market_line` stays blank until a league or licensed source publishes prices: filling it from a mirror
would put a third-party number under an official-sounding column name, which is the one thing the source
rule forbids. The mirror's numbers are still worth having, so they get their OWN labelled columns instead
of a borrowed one:

  mirror_close_line            the mirror's closing line for that market
  mirror_close_source_type     `third-party-mirror`, on every row
  mirror_close_verification    `unverified-third-party`, on every row
  mirror_close_bytes_sha256    sha256 of the pinned file the value was read from
  residual_vs_mirror_close     our_line - mirror_close_line, arithmetic only

Publishing the residual on a labelled basis is what lets "price every line and publish the residual" run
from day one without a price authority that does not exist: the number states its own source. It is not
closing line value — no wager was made at either price — and the column says so. Opening captures stay
blank: the mirror carries one price set per market, and inventing an "open" from a closing file is the
inference the repository forbids.

Capture integrity is part of the record. A stage that was not captured in time
is stored with an explicit status (`pending_kickoff`, `not_captured_before_kickoff`,
`captured_post_final`) instead of being back-filled with the open value. The
repository snapshot clock is 2026-11-14, which is AFTER the Week 10 Thursday
final — that game's captures are post-hoc and the store says so.

Usage
-----
  python3 tools/build_snapshots.py           # build + verify
  python3 tools/build_snapshots.py --check   # also fail if the commit is stale
"""

from __future__ import annotations

import csv
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "snapshots")
SNAPSHOT = "2026-11-14"          # the date the captures below were taken
REBUILT = "2026-11-17"           # the date the Week 10 closure moved this store's inputs
MARKETS = [("side", 1), ("total", 2), ("moneyline", 3)]   # origination order S3
FEED = "data/results/verified_results.json"
MIRROR_FILE = "data/raw/nflverse/games.csv"
MANIFEST = "data/raw_manifest.json"
# The three sets spell the two relocated clubs differently (official standings page AZ, Week 10 PSV ARI,
# mirror LA). Normalise for joins only; every published value keeps the spelling its own source prints.
CODE = {"ARZ": "ARI", "AZ": "ARI", "LAR": "LA", "WSH": "WAS"}


def norm(code: str) -> str:
    return CODE.get(str(code).strip().upper(), str(code).strip().upper())


def load_feed() -> dict:
    """(away, home, gameday) -> the settled row, from the verified results feed.

    Joined on matchup and date rather than on game_id, because the feed's id for one Week 10 fixture is
    `2026_10_LA_AZ` while the origination file's is `2026_10_LA_ARI`: an id join would have dropped that
    game in silence. Measured on 2026-11-17, not assumed.
    """
    doc = json.load(open(os.path.join(ROOT, FEED), encoding="utf-8"))
    out = {}
    for r in doc["rows"]:
        out[(norm(r["away_team"]), norm(r["home_team"]), r["gameday"])] = r
    return out


def load_mirror_prices() -> tuple[dict, dict]:
    """The mirror's price set, read from the BYTES rather than from a derived file, so the sha256
    published beside every price is the sha256 of the file the price was read from."""
    import hashlib
    path = os.path.join(ROOT, MIRROR_FILE)
    raw = open(path, "rb").read()
    digest = hashlib.sha256(raw).hexdigest()
    man = json.load(open(os.path.join(ROOT, MANIFEST), encoding="utf-8"))
    entry = next((e for e in man if e.get("name") == "games.csv"), {})
    if entry.get("sha256") != digest:
        raise SystemExit(
            f"FAIL: {MIRROR_FILE} on disk (sha256 {digest[:16]}..) is not the bytes {MANIFEST} pins "
            f"(sha256 {str(entry.get('sha256'))[:16]}..). Every price in this store is cited by pin, so "
            "a file that moved must stop the build instead of quietly moving the numbers.")
    out = {}
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        if r.get("season") != "2026" or r.get("game_type") != "REG":
            continue
        out[(norm(r["away_team"]), norm(r["home_team"]), r["gameday"])] = r
    pin = {"file": MIRROR_FILE, "sha256": digest, "bytes": len(raw),
           "retrieved_at": entry.get("retrieved_at", ""), "url": entry.get("url", ""),
           "upstream": f"{entry.get('repo', '')}/{entry.get('path', '')}"}
    return out, pin


def load_originated() -> list[dict]:
    path = os.path.join(ROOT, "data", "lines", "originated_lines_2026_week10.csv")
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def build() -> dict:
    games = load_originated()
    if len(games) != 14:
        raise SystemExit(f"FAIL: expected 14 originated games, found {len(games)}")
    feed = load_feed()
    mirror, pin = load_mirror_prices()
    missing = []
    for g in games:
        k = (norm(g["away"]), norm(g["home"]), g["date"])
        g["_feed"] = feed.get(k)
        g["_mirror"] = mirror.get(k, {})
        g["_played_now"] = bool(g["_feed"] and g["_feed"].get("status") == "final")
        if k not in mirror:
            missing.append(g["game_id"])
    if missing:
        raise SystemExit(f"FAIL: no mirror row to price these games: {missing}")

    records = []
    for g in games:
        game_id = g["game_id"]
        # `played` as the origination file recorded it on 2026-11-14 is a point-in-time statement and is
        # kept as such; `played_at_build` is what the closed feed says today. The two differ for 13 games
        # and that difference IS the capture story, so both are published.
        played = str(g.get("played", "")).strip().upper() == "Y"
        played_now = g["_played_now"]
        fr = g["_feed"] or {}
        mr = g["_mirror"]
        for market, seq in MARKETS:
            if market == "side":
                our_line = g["x1_spread_away"]
                our_alt = ""
                our_label = f"{g['away']} spread {our_line}"
            elif market == "total":
                our_line = g["x1_total"]
                our_alt = ""
                our_label = f"game total {our_line}"
            else:
                our_line = g["x1_ml_away"]
                our_alt = g["x1_ml_home"]
                our_label = f"{g['away']} {our_line} / {g['home']} {our_alt}"

            common = {
                "game_id": game_id,
                "gameday": g["date"],
                "away_team": g["away"],
                "home_team": g["home"],
                "market": market,
                "origination_sequence": seq,
                "our_line": our_line,
                "our_line_alt": our_alt,
                "our_line_label": our_label,
                "market_line": "",
                "market_line_alt": "",
                "difference": "",
                "market_line_status": (
                    "blocked — no official source publishes betting prices (Q-02)"
                ),
                "source_url": "https://www.nfl.com/schedules/2026/by-week/week-10",
                "model_source": "data/lines/originated_lines_2026_week10.csv",
                # ---- settlement, from the verified results feed (official pages only) ----
                "result_official": (f"{fr['away_score']}-{fr['home_score']}"
                                    if fr.get("status") == "final" else ""),
                "result_source_url": fr.get("game_url", ""),
                "result_read_at": fr.get("retrieved_at", ""),
                "played_at_build": "Y" if played_now else "N",
            }

            # ---- the labelled third-party capture (never written into market_line) ----
            key = {"side": "spread_line", "total": "total_line",
                   "moneyline": "away_moneyline"}[market]
            alt_key = {"side": "", "total": "", "moneyline": "home_moneyline"}[market]
            mline = str(mr.get(key, "")).strip()
            malt = str(mr.get(alt_key, "")).strip() if alt_key else ""
            resid = ""
            if mline and mline.lower() not in ("none", "nan"):
                try:
                    resid = f"{float(str(our_line)) - float(mline):+.1f}"
                except ValueError:
                    resid, mline, malt = "", "", ""
            mirror_block = {
                "mirror_close_line": mline,
                "mirror_close_line_alt": malt,
                "mirror_close_price_kind": "line" if market != "moneyline" else "odds",
                "mirror_close_captured_at": pin["retrieved_at"],
                "mirror_close_source_url": "https://github.com/nflverse/nfldata/blob/master/data/games.csv",
                "mirror_close_source_type": "third-party-mirror",
                "mirror_close_verification": "unverified-third-party",
                "mirror_close_bytes_sha256": pin["sha256"],
                "residual_vs_mirror_close": resid,
                "residual_basis": ("our originated line minus the mirror's closing line. Third-party, "
                                   "unverified, not a residual against an official price, and not "
                                   "closing line value: no bet was placed at either number."),
                "opening_mirror_line": "",
                "opening_mirror_status": ("the mirror carries one price set per market; no opening "
                                          "capture exists and none is back-filled (Q-02/Q-03)"),
            }

            # ---- open stage ----
            if played:
                open_rec = {
                    **common,
                    "stage": "open",
                    "captured_at": SNAPSHOT,
                    "status": "captured_post_final",
                    "status_note": (
                        "The repository snapshot clock (2026-11-14) is after this game's "
                        "kickoff (2026-11-12), so this record cannot serve as a true opening "
                        "capture. Recorded as-is, flagged, never back-dated."
                    ),
                }
                close_rec = {
                    **common,
                    "stage": "close",
                    "captured_at": "",
                    "status": "not_captured_before_kickoff",
                    "status_note": (
                        "No close capture exists for this game: the store went live after the "
                        "final. Left blank rather than filled with the open value."
                    ),
                }
            elif played_now:
                # The store went live before kickoff, no close capture was taken at kickoff, and the game
                # has since been settled from official pages. `pending_kickoff` would be a false statement
                # about today; back-filling the open value into the close stage would be a fabricated
                # capture. So the status names the gap instead.
                open_rec = {
                    **common,
                    "stage": "open",
                    "captured_at": SNAPSHOT,
                    "status": "recorded",
                    "status_note": (f"Captured on {SNAPSHOT}, before this game's kickoff ({g['date']}). "
                                    "The origination file still records this game as unplayed because that "
                                    "file is the 2026-11-14 point-in-time record; the settled result "
                                    "beside it comes from the closed results feed."),
                }
                close_rec = {
                    **common,
                    "stage": "close",
                    "captured_at": "",
                    "status": "not_captured_before_kickoff",
                    "status_note": ("No close capture exists: the store was written before kickoff and "
                                    "the scheduled close capture was not taken. Left blank rather than "
                                    "filled with the open value. The mirror's closing line is published "
                                    "separately, in labelled columns."),
                }
            else:
                open_rec = {
                    **common,
                    "stage": "open",
                    "captured_at": SNAPSHOT,
                    "status": "recorded",
                    "status_note": "Captured before kickoff.",
                }
                close_rec = {
                    **common,
                    "stage": "close",
                    "captured_at": "",
                    "status": "pending_kickoff",
                    "status_note": (
                        "Close capture is taken at kickoff by the scheduled pipeline; this "
                        "game had not kicked off at the snapshot clock."
                    ),
                }
            open_rec.update(mirror_block)
            close_rec.update(mirror_block)
            records.append(open_rec)
            records.append(close_rec)

    # invariants
    if len(records) != 14 * 3 * 2:
        raise SystemExit(f"FAIL: expected 84 records, built {len(records)}")
    n_resid = n_mirror = 0
    for r in records:
        if r["market_line"] != "":
            raise SystemExit(f"FAIL: {r['game_id']} market_line must stay blank (Q-02)")
        if r["difference"] != "":
            raise SystemExit(f"FAIL: {r['game_id']} difference must stay blank while market is blank")
        # the labelled channel is where third-party numbers live, and only there
        if r["mirror_close_line"] and r["mirror_close_verification"] != "unverified-third-party":
            raise SystemExit(f"FAIL: {r['game_id']} carries a mirror price without its label")
        if r["mirror_close_line"]:
            n_mirror += 1
        if r["residual_vs_mirror_close"]:
            n_resid += 1
            want = float(r["our_line"]) - float(r["mirror_close_line"])
            if abs(want - float(r["residual_vs_mirror_close"])) > 0.051:
                raise SystemExit(f"FAIL: {r['game_id']} residual is not the arithmetic")
        if not r["mirror_close_line"] and r["residual_vs_mirror_close"]:
            raise SystemExit(f"FAIL: {r['game_id']} has a residual with no price to subtract")
        if r["opening_mirror_line"]:
            raise SystemExit("FAIL: an opening mirror capture appeared from nowhere - the mirror has one "
                             "price set per market and a second stage must not be invented")
        if r["stage"] == "close" and r["status"] == "pending_kickoff" and r["played_at_build"] == "Y":
            raise SystemExit(f"FAIL: {r['game_id']} is settled but its close stage says pending")
        if (r["stage"] == "close" and r["status"] == "not_captured_before_kickoff"
                and r["played_at_build"] == "N" and r["gameday"] >= REBUILT):
            raise SystemExit(f"FAIL: {r['game_id']} is unplayed; its close stage must say pending")
        if not str(r["model_source"]).endswith(".csv"):
            raise SystemExit("FAIL: record without a model source")

    from collections import Counter
    status_counts = Counter(r["status"] for r in records)
    settled_now = len({r["game_id"] for r in records if r["played_at_build"] == "Y"})

    return {
        "dataset": "price_snapshots",
        "title": "Price-snapshot store — opening and closing numbers for every market we originate",
        "generated_at": SNAPSHOT,
        "rebuilt_at": REBUILT,
        "contract": {
            "markets_per_game": ["side", "total", "moneyline"],
            "origination_order": "side first, then total, then moneyline (S3)",
            "stages_per_market": ["open", "close"],
            "our_line": "our own originated number — computed by the repo model, always recorded",
            "market_line": (
                "the market's number at that stage — recorded only from an official source; "
                "blank and flagged today because no league or club source publishes prices (Q-02)"
            ),
            "difference": (
                "fair line minus market line — must stay blank while market_line is blank; "
                "never derived from a third-party number"
            ),
            "capture_rule": (
                "a stage not captured in time keeps its status and an empty value; it is never "
                "back-filled from the other stage"
            ),
            "mirror_rule": (
                "third-party prices live only in the mirror_* columns, each row carrying its "
                "verification state and the sha256 of the pinned file it was read from; they are never "
                "copied into market_line, and no opening value is back-filled from a closing file "
                "(price-data policy decision, 2026-11-17)"
            ),
        },
        "rows_count": len(records),
        "columns": [
            "game_id", "gameday", "market", "origination_sequence", "stage",
            "captured_at", "status", "our_line", "our_line_alt", "market_line",
            "market_line_alt", "difference", "source_url", "model_source",
            "result_official", "result_source_url", "result_read_at", "played_at_build",
            "mirror_close_line", "mirror_close_line_alt", "mirror_close_price_kind",
            "mirror_close_captured_at", "mirror_close_source_url", "mirror_close_source_type",
            "mirror_close_verification", "mirror_close_bytes_sha256",
            "residual_vs_mirror_close", "residual_basis",
            "opening_mirror_line", "opening_mirror_status",
        ],
        "source": {
            "url": "https://www.nfl.com/schedules/2026/by-week/week-10",
            "label": "NFL.com Week 10 schedule (the games these markets are originated on)",
            "org": "NFL",
        },
        "status_counts": dict(status_counts),
        "verification": {
            "records": len(records),
            "games": 14,
            "markets_per_game": 3,
            "stages_per_market": 2,
            "market_line_values_published": 0,
            "market_line_blank_and_flagged": len(records),
            "games_settled_from_the_official_feed": settled_now,
            "mirror_labelled_prices_published": n_mirror,
            "residuals_published_on_the_labelled_basis": n_resid,
            "opening_mirror_captures": 0,
            "violations": 0,
        },
        "price_provenance": {
            "mirror_pin": pin,
            "policy": ("2026-11-17: publish the mirror's numbers in labelled columns, never as an "
                       "official price; keep opening blank until a licensed feed exists; state that a "
                       "residual against an unverified price is not closing line value"),
            "results_feed": {"file": FEED,
                             "joined_on": "away+home+gameday (game_id spelling differs between sources)"},
        },
        "note": (
            "This store is append-ready: tools/build_snapshots.py regenerates it from the "
            "origination file, the closed results feed and the fingerprinted mirror. When an official "
            "price source is settled (Q-02), market_line and difference fill from recorded captures "
            "only; the mirror columns never migrate into them."
        ),
        "rows": records,
    }


def main() -> int:
    store = build()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "price_snapshots.json"), "w", encoding="utf-8") as fh:
        json.dump(store, fh, indent=1)
        fh.write("\n")

    cols = store["columns"]
    with open(os.path.join(OUT, "price_snapshots.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in store["rows"]:
            w.writerow(r)

    v = store["verification"]
    print(
        f"price_snapshots: {store['rows_count']} records, "
        f"statuses={store['status_counts']}, "
        f"market_line published=0 (all blank+flagged), "
        f"mirror-labelled prices={v['mirror_labelled_prices_published']}, "
        f"residuals={v['residuals_published_on_the_labelled_basis']}, "
        f"settled from the feed={v['games_settled_from_the_official_feed']}/14"
    )

    if "--check" in sys.argv:
        rel = ["data/snapshots/price_snapshots.json", "data/snapshots/price_snapshots.csv"]
        out = subprocess.run(["git", "diff", "--exit-code", "--"] + rel,
                             cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            print("FAIL: committed snapshot store is stale")
            print(out.stdout[:2000])
            return 1
        print("check: committed snapshot store matches a fresh build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
