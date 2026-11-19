#!/usr/bin/env python3
"""Recompute every machine-checkable headline number on the landing page.

Session arena/525b792a-x1 (task LA-1). The landing page (index.html) states numbers
such as "347 week-10 injury rows" or "42 met". Those numbers come from generator
constants. This tool recomputes each one from the committed file it claims to
describe, then checks that the landing text states the same value. Any drift fails.

Each claim records: the landing phrase it must find, the recomputed value, the
file the value was read from, and the official source of the underlying data.
Claims that cannot be recomputed offline are listed as `not_machine_checked`
rather than silently passed.

Usage:
  python3 tools/audit_landing_numbers.py           # write data/audit/landing_numbers.json
  python3 tools/audit_landing_numbers.py --check   # exit 1 on any failure or stale output
"""
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
OUT = ROOT / "data" / "audit" / "landing_numbers.json"
REQ = ROOT / "data" / "audit" / "requirements_assessed.json"
INJ = ROOT / "data" / "nfl" / "injuries_week10.tsv"
STD = ROOT / "data" / "nfl" / "standings.tsv"
SCH = ROOT / "data" / "nfl" / "schedule_week10.tsv"

SRC_INJ = "https://www.nfl.com/injuries/"
SRC_STD = "https://www.nfl.com/standings/league/2026/REG"
SRC_SCH = "https://www.nfl.com/schedules/2026/by-week/week-10"


def landing_text() -> str:
    html = INDEX.read_text(encoding="utf-8")
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    return re.sub(r"\s+", " ", text)


def tsv_rows(path: Path) -> list[dict]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.startswith("#")]
    return list(csv.DictReader(lines, delimiter="\t"))


FINALS_TODAY = ROOT / "data" / "audit" / "w10_finals_independent_read_2026_11_19.psv"
FINALS_NOV17 = ROOT / "data" / "evidence" / "2026_11_17" / "week10_finals.tsv"


def finals_cross_check() -> dict:
    """Compare the 2026-11-19 independent read of the 14 official Week 10 finals with the
    repository's 2026-11-17 closure file, row by row on game, away, away_score, home, home_score."""
    def load(path, cols_map):
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.startswith("#")]
        out = {}
        for r in csv.DictReader(lines, delimiter="|"):
            key = r[cols_map["id"]]
            out[key] = tuple(r[cols_map[c]] for c in ("away", "away_score", "home", "home_score"))
        return out
    today = load(FINALS_TODAY, {"id": "game_id", "away": "away", "away_score": "away_score",
                                "home": "home", "home_score": "home_score"})
    closure = load(FINALS_NOV17, {"id": "game_id", "away": "away", "away_score": "away_score",
                                  "home": "home", "home_score": "home_score"})
    mismatches = [k for k in today if closure.get(k) != today[k]]
    missing = sorted(set(today) ^ set(closure))
    return {"games_read_today": len(today), "games_in_nov17_closure": len(closure),
            "compared": len(set(today) & set(closure)), "mismatches": mismatches,
            "unmatched_ids": missing}


def cells_compared() -> tuple[int, int]:
    """Run the independent cell-by-cell check and parse its summary line."""
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "verify_against_official.py")],
                       capture_output=True, text=True, cwd=ROOT, timeout=600)
    m = re.search(r"cells compared:\s*([\d,]+)\s+mismatches:\s*(\d+)", r.stdout)
    if r.returncode != 0 or not m:
        raise SystemExit("verify_against_official.py did not produce a cell summary")
    return int(m.group(1).replace(",", "")), int(m.group(2))


def main() -> int:
    text = landing_text()
    req = json.loads(REQ.read_text(encoding="utf-8"))["counts"]
    inj_rows = tsv_rows(INJ)
    std_rows = tsv_rows(STD)
    sch_rows = tsv_rows(SCH)
    cells, mismatches = cells_compared()
    fx = finals_cross_check()
    sched_scheduled = sum(1 for r in sch_rows if r["status"].strip() == "scheduled")

    claims = [
        {"id": "LA-N01", "label": "requirements tracked", "value": req["total"],
         "landing_phrase": f"{req['total']} requirements", "file": "data/audit/requirements_assessed.json",
         "source": "docs/live-pipeline/project-brief.md (owner brief)"},
        {"id": "LA-N02", "label": "requirements met", "value": req["met"],
         "landing_phrase": f"{req['met']} met", "file": "data/audit/requirements_assessed.json",
         "source": "repository assessment (see pages/requirements.html)"},
        {"id": "LA-N03", "label": "requirements partly met", "value": req["partly_met"],
         "landing_phrase": f"{req['partly_met']} partly met", "file": "data/audit/requirements_assessed.json",
         "source": "repository assessment (see pages/requirements.html)"},
        {"id": "LA-N04", "label": "requirements open", "value": req["open"],
         "landing_phrase": f"{req['open']} open", "file": "data/audit/requirements_assessed.json",
         "source": "repository assessment (see pages/requirements.html)"},
        {"id": "LA-N05", "label": "week-10 injury rows", "value": len(inj_rows),
         "landing_phrase": f"{len(inj_rows)} week-10 injury rows", "file": "data/nfl/injuries_week10.tsv",
         "source": SRC_INJ},
        {"id": "LA-N06", "label": "clubs in standings", "value": len(std_rows),
         "landing_phrase": f"{len(std_rows)} teams", "file": "data/nfl/standings.tsv",
         "source": SRC_STD},
        {"id": "LA-N07", "label": "week-10 games in schedule", "value": len(sch_rows),
         "landing_phrase": f"{len(sch_rows)} week-10 games", "file": "data/nfl/schedule_week10.tsv",
         "source": SRC_SCH},
        {"id": "LA-N08", "label": "cells compared against official page", "value": cells,
         "landing_phrase": f"{cells:,} cells", "file": "tools/verify_against_official.py (run)",
         "source": f"{SRC_INJ} · {SRC_STD} · {SRC_SCH}"},
        {"id": "LA-N09", "label": "cell mismatches", "value": mismatches,
         "landing_phrase": f"{mismatches} mismatches", "file": "tools/verify_against_official.py (run)",
         "source": f"{SRC_INJ} · {SRC_STD} · {SRC_SCH}"},
    ]
    for c in claims:
        c["landing_states_value"] = c["landing_phrase"] in text
        c["pass"] = bool(c["landing_states_value"])
    # Finals: the 2026-11-19 independent read must agree with the 2026-11-17 closure file.
    claims.append({"id": "LA-N11", "label": "week-10 finals re-read 2026-11-19 vs 2026-11-17 closure (mismatching games)",
                   "value": len(fx["mismatches"]) + len(fx["unmatched_ids"]),
                   "landing_phrase": None, "file": "data/audit/w10_finals_independent_read_2026_11_19.psv"
                   " vs data/evidence/2026_11_17/week10_finals.tsv",
                   "source": "https://www.nfl.com/schedules/2026/by-week/week-10",
                   "detail": fx,
                   "landing_states_value": None,
                   "pass": not fx["mismatches"] and not fx["unmatched_ids"] and fx["games_read_today"] == 14})

    # Stale states, recorded so the reader can see them. These do not fail the build: the landing
    # text is dated (2026-11-16) and the schedule file is a dated 2026-11-14 snapshot.
    notes_stale = [
        {"id": "LA-N12",
         "finding": ("The landing's '13 / 14 Week 10 games officially final' is dated to a 2026-11-16 read "
                     "('the Monday-night game was still unplayed at read time'). The official page read on "
                     "2026-11-19 shows all 14 games FINAL, and the 2026-11-17 closure file agrees."),
         "source": "https://www.nfl.com/schedules/2026/by-week/week-10",
         "action": "integration request LA-4 (landing text) — flagged, not edited here"},
        {"id": "LA-N13",
         "finding": (f"data/nfl/schedule_week10.tsv is the 2026-11-14 snapshot: {sched_scheduled} of "
                     f"{len(sch_rows)} rows still read status 'scheduled' with blank scores. "
                     "The official page shows them FINAL."),
         "file": "data/nfl/schedule_week10.tsv",
         "source": "https://www.nfl.com/schedules/2026/by-week/week-10",
         "action": "dated snapshot kept as evidence; the current state is in the 2026-11-19 read"},
    ]

    # Known, deliberately reported omission: the landing page's "open" count leaves out
    # the requirements the register marks "in progress". Recorded, not hidden.
    notes = [{
        "id": "LA-N10",
        "finding": (f"{req['in_progress']} requirements are 'in progress' and are not in the landing "
                    f"page's '{req['open']} open' count (register total {req['total']} = "
                    f"{req['met']} met + {req['partly_met']} partly met + {req['open']} open + "
                    f"{req['in_progress']} in progress)."),
        "action": "integration request LA-4 (tools/build_site.py, owned by the integration session)",
    }]
    not_machine_checked = [
        "'8 week-11 checks passed' (decision room, room/index.html): no offline recomputation exists",
        "'160 / 160' and '13 / 14' reconciliation figures: produced by other builders, not recomputed here",
        "'+0.109' model-vs-market figure: produced by the research builders, not recomputed here",
    ]
    failed = [c["id"] for c in claims if not c["pass"]]
    fx_pass = not fx["mismatches"] and not fx["unmatched_ids"] and fx["games_read_today"] == 14
    if not fx_pass and "LA-N11" not in failed:
        failed.append("LA-N11")
    doc = {
        "title": "Landing-page number audit",
        "session": "arena/525b792a-x1",
        "task": "LA-1",
        "method": ("Each claim is recomputed from the committed file named in `file`, then the "
                   "landing text (index.html, tags stripped) must contain the exact `landing_phrase`. "
                   "A mismatch in either direction fails tools/audit_landing_numbers.py --check."),
        "landing_page": "index.html",
        "claims": claims,
        "notes": notes + notes_stale,
        "finals_cross_check": {k: v for k, v in fx.items()},
        "not_machine_checked": not_machine_checked,
        "summary": {"claims": len(claims), "passed": len(claims) - len(failed), "failed": failed},
    }
    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

    if "--check" in sys.argv:
        ok_committed = OUT.exists() and OUT.read_text(encoding="utf-8") == body
        if failed or not ok_committed:
            print("FAIL:", failed or "committed landing_numbers.json is stale")
            return 1
        print(f"landing numbers: {len(claims)} claims, all match the committed data")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(claims) - len(failed)}/{len(claims)} claims pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
