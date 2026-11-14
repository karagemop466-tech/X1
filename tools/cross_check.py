#!/usr/bin/env python3
"""Second-pass cross-check of this session's transcriptions against an independent one.

Two sessions transcribed the same official NFL pages separately. Where they agree, a
typo is much less likely; where they disagree, at least one is wrong. This is the
independent second pass that docs/suggestions called for (S-10) and it is now a tool,
not a claim.

Inputs (both present in this repo after the main merge):
  data/nfl/standings.tsv          (this session, division-grouped)
  data/standings_2026.csv         (parallel session, independent read)
  data/nfl/injuries_week10.tsv    (this session)
  data/injuries_2026_week10.csv   (parallel session)

Exits non-zero on any disagreement so CI can hold the line.
"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors = []


def tsv(path):
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


# ---------------- standings ----------------
st_mine = {r["abbr"]: r for r in tsv(ROOT / "data/nfl/standings.tsv")}
st_thr = {r["team_abbr"]: r for r in csv.DictReader((ROOT / "data/standings_2026.csv").open(encoding="utf-8"))}
# the two use different codes for the Rams; normalise explicitly rather than fuzzy-match
ALIAS = {"LA": "LAR"}
st_thr = {ALIAS.get(k, k): v for k, v in st_thr.items()}

if set(st_mine) != set(st_thr):
    errors.append(f"standings: club sets differ (only mine {sorted(set(st_mine)-set(st_thr))}, "
                  f"only theirs {sorted(set(st_thr)-set(st_mine))})")

FIELDS = (("W", "w"), ("L", "l"), ("T", "t"), ("PF", "pf"), ("PA", "pa"), ("NET_PTS", "diff"))
compared = 0
for club in sorted(set(st_mine) & set(st_thr)):
    for theirs_f, mine_f in FIELDS:
        compared += 1
        if str(st_thr[club][theirs_f]).strip() != str(st_mine[club][mine_f]).strip():
            errors.append(f"standings {club} {theirs_f}: theirs={st_thr[club][theirs_f]} mine={st_mine[club][mine_f]}")
    try:
        compared += 1
        if abs(float(st_thr[club]["PCT"]) - float(st_mine[club]["pct"])) > 5e-4:
            errors.append(f"standings {club} PCT: theirs={st_thr[club]['PCT']} mine={st_mine[club]['pct']}")
    except (TypeError, ValueError):
        errors.append(f"standings {club}: unparseable PCT")

# ---------------- injuries ----------------
inj_mine = tsv(ROOT / "data/nfl/injuries_week10.tsv")
inj_thr = list(csv.DictReader((ROOT / "data/injuries_2026_week10.csv").open(encoding="utf-8")))
mk = {(r["team"], r["player"].strip()): r for r in inj_mine}
tk = {(r["team_abbr"], r["player"].strip()): r for r in inj_thr}
if set(mk) != set(tk):
    errors.append(f"injuries: row sets differ (only mine {len(set(mk)-set(tk))}, only theirs {len(set(tk)-set(mk))})")
cells = 0
for key in sorted(set(mk) & set(tk)):
    for f in ("position", "injury", "practice_status", "game_status"):
        cells += 1
        a = (tk[key][f] or "").strip()
        b = (mk[key][f] or "").strip()
        if a != b:
            errors.append(f"injuries {key} {f}: theirs={a!r} mine={b!r}")

print(f"standings clubs compared : {len(set(st_mine) & set(st_thr))}  fields: {compared}")
print(f"injury rows compared     : {len(set(mk) & set(tk))}  cells: {cells}")
if errors:
    print(f"\nDISAGREEMENTS ({len(errors)}):")
    for e in errors[:40]:
        print("  -", e)
    sys.exit(1)
print("two independent transcriptions agree on every compared value")
