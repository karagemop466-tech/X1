#!/usr/bin/env python3
"""Build the auditable requirement decision-readiness matrix.

Inputs are the reviewed requirement assessment and the pre-registered validation gates.
The builder never invents numeric thresholds or maps a project requirement to an NFL source
that was not recorded in the assessment. `--check` verifies reproducibility without writing.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "data/audit/requirements_assessed.json"
GATES = ROOT / "data/gates.json"
OUT_JSON = ROOT / "data/readiness/decision_readiness.json"
OUT_HTML = ROOT / "pages/readiness.html"
REPO = "https://github.com/karagemop466-tech/X1/blob/main/"


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


REQ_GATE_MAP = {
    # These mappings are explicit to the assessed register IDs; they are not inferred from a row's prose.
    "R-07": ["G0", "G6"],
    "R-08": ["G1", "G2", "G3", "G4", "G6"],
    "R-09": ["G1", "G2", "G3", "G4", "G5", "G6"],
    "R-10": ["G1", "G2", "G3", "G4", "G5", "G6"],
    "R-11": ["G1", "G7"],
    "R-12": ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7"],
    "R-13": ["G7"],
    "R-14": ["G2", "G3", "G4", "G5"],
    "R-15": ["G0"], "R-16": ["G0"], "R-17": ["G0"],
    "R-46": ["G0", "G6"], "R-47": ["G0", "G6"],
    "R-48": ["G0", "G6"], "R-49": ["G0", "G6"],
    "R-50": ["G1", "G2", "G3", "G4", "G5", "G6"],
    "R-51": ["G0"], "R-52": ["G7"], "R-53": ["G1", "G2", "G3", "G4", "G5", "G6"],
}


def gate_for(row: dict, gates: dict) -> tuple[str, str, str]:
    """Return the explicitly mapped gate and only registered clearing criteria."""
    if row["state"] == "met":
        return ("None — assessed met", "Already marked met in the reviewed requirement register.", "")

    ids = REQ_GATE_MAP.get(row["id"], [])
    if not ids:
        return (
            "Evidence / owner-decision gate (no numbered gate registered)",
            "Provide the evidence or recorded decision named in the assessment; this register contains no numeric threshold for this requirement.",
            "",
        )

    by_id = {g["id"]: g for g in gates["gates"]}
    labels = "; ".join(f"{gate_id} — {by_id[gate_id]['name']}" for gate_id in ids)
    rules = []
    numeric = []
    for gate_id in ids:
        gate = by_id[gate_id]
        thresholds = gate.get("thresholds", {})
        if thresholds:
            entries = ", ".join(f"{name.replace('_', ' ')} ≥ {value}" for name, value in thresholds.items())
            rules.append(f"{gate_id}: {entries}; assess on effective sample size (n_eff), not raw n.")
            numeric.extend(f"{name}={value}" for name, value in thresholds.items())
        criteria = gate.get("criteria", [])
        if criteria:
            rules.append(f"{gate_id}: " + "; ".join(criteria) + ".")
    if not rules:
        rules.append("The registered gate has no numeric criterion; no number is supplied here.")
    return labels, " ".join(rules), "; ".join(numeric)


def build_payload() -> dict:
    assessment = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
    gates = json.loads(GATES.read_text(encoding="utf-8"))
    rows = assessment.get("rows", [])
    expected = assessment.get("counts", {}).get("total")
    if not rows or len(rows) != expected:
        raise SystemExit(f"requirement count mismatch: expected {expected}, found {len(rows)}")
    ids = [r.get("id") for r in rows]
    if len(set(ids)) != len(ids) or any(not i for i in ids):
        raise SystemExit("requirement IDs must be present and unique")

    output = []
    for row in rows:
        if not row.get("evidence_url", "").startswith("https://") or not row.get("brief_source", "").startswith("https://"):
            raise SystemExit(f"missing HTTPS evidence/brief source for {row.get('id')}")
        blocker, clearance, number = gate_for(row, gates)
        output.append({
            "id": row["id"],
            "category": row["category"],
            "requirement": row["requirement"],
            "assessment_status": row["state"],
            "assessment_note": row["assessment"],
            "blocking_gate": blocker,
            "clearance_criterion": clearance,
            "registered_numeric_threshold": number,
            "evidence_url": row["evidence_url"],
            "requirement_source_url": row["brief_source"],
            "official_nfl_source_url": None,
            "source_note": "No direct official NFL URL is recorded against this requirement row. The project brief/evidence links below are not represented as NFL sources; any NFL-specific fact remains subject to its linked evidence page and source registry.",
            "source_flag": "REQUIREMENT_SOURCE_ONLY",
            "row_review_flag": "Conflicting pass/promotion summaries exist in separate site trees; see the cross-tree conflict disclosure above." if row["id"] == "R-08" else "",
        })

    counts = assessment["counts"]
    return {
        "generated_from": [str(ASSESSMENT.relative_to(ROOT)), str(GATES.relative_to(ROOT))],
        "assessment_date": assessment.get("generated_at"),
        "tracked_requirement_count": len(output),
        "assessment_counts": counts,
        "coverage_warning": "This matrix covers only the 53 requirement rows in requirements_assessed.json. The later detailed additions in the latest owner brief are not individually cross-walked here; do not treat this count as complete coverage of every added statement.",
        "threshold_policy": "Only thresholds explicitly present in data/gates.json are shown. Blank threshold means no registered numeric clearance value; no number was inferred. This is not a canonical cross-tree gate choice.",
        "cross_tree_conflicts": [
            {
                "issue": "G1 sample-size threshold differs by tree",
                "root_register": "data/gates.json: effective sample thresholds are 500 singles, 300 two-leg parlay tickets, 400 three-plus-leg tickets, 500 prop tickets.",
                "console_register": "console/gates.html: G1 is at least 200 settled out-of-sample bets.",
                "resolution": "Unresolved. This matrix displays the root register only; strategy clearance must remain blocked until the canonical gate and market-specific rules are reconciled.",
                "sources": ["https://github.com/karagemop466-tech/X1/blob/main/data/gates.json", "https://github.com/karagemop466-tech/X1/blob/main/console/gates.html"]
            },
            {
                "issue": "Conflicting strategy pass summaries",
                "root_register": "docs/audit/EXECUTIVE-SUMMARY.md says one of sixteen strategies passes all eight gates.",
                "console_register": "console/gates.html shows zero strategies live / promoted.",
                "resolution": "Unresolved across different strategy/gate trees. Do not combine these results or describe a single repo-wide promotion count until definitions and windows are reconciled.",
                "sources": ["https://github.com/karagemop466-tech/X1/blob/main/docs/audit/EXECUTIVE-SUMMARY.md", "https://github.com/karagemop466-tech/X1/blob/main/console/gates.html"]
            }
        ],
        "rows": output,
    }


def render(payload: dict) -> str:
    counts = payload["assessment_counts"]
    summary = " · ".join(f"{key.replace('_', ' ')}: {counts.get(key, 0)}" for key in ("met", "partly_met", "open", "in_progress"))
    body_rows = []
    for row in payload["rows"]:
        state = esc(row["assessment_status"].replace("_", " "))
        badge_class = "ok" if row["assessment_status"] == "met" else "warn"
        review_badge = f'<span class="pill warn">{esc(row["row_review_flag"])}</span>' if row["row_review_flag"] else ""
        number = esc(row["registered_numeric_threshold"]) if row["registered_numeric_threshold"] else "<span class=\"pill warn\" title=\"No numeric threshold is registered; none has been inferred\">— not set</span>"
        body_rows.append(
            "<tr>"
            f"<td><b>{esc(row['id'])}</b></td>"
            f"<td>{esc(row['category'])}</td>"
            f"<td><b>{esc(row['requirement'])}</b><details><summary>Assessment notes</summary><p>{esc(row['assessment_note'])}</p></details>{review_badge}</td>"
            f"<td><span class=\"pill {badge_class}\">{state}</span></td>"
            f"<td>{esc(row['blocking_gate'])}</td>"
            f"<td>{esc(row['clearance_criterion'])}</td>"
            f"<td>{number}</td>"
            f"<td><a class=\"src-link\" href=\"{esc(row['evidence_url'])}\" target=\"_blank\" rel=\"noopener noreferrer\">Evidence ↗</a><br>"
            f"<a class=\"src-link\" href=\"{esc(row['requirement_source_url'])}\" target=\"_blank\" rel=\"noopener noreferrer\">Project brief ↗</a><br>"
            "<span class=\"pill warn\" title=\"No direct official NFL URL is recorded for this requirement row\">NFL source not recorded</span></td>"
            "</tr>"
        )

    conflicts_html = "".join(
        "<li><b>" + esc(item["issue"]) + ":</b> " + esc(item["root_register"]) + " " + esc(item["console_register"]) + " " + esc(item["resolution"]) + " " + " · ".join(
            f'<a class="src-link" href="{esc(url)}" target="_blank" rel="noopener noreferrer">source ↗</a>' for url in item["sources"]
        ) + "</li>"
        for item in payload["cross_tree_conflicts"]
    )

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Decision readiness — Fourth Down</title>
<meta name="description" content="Requirement-by-requirement blockers, registered clearance criteria and source gaps.">
<link rel="stylesheet" href="../assets/site.css">
</head><body>
<a class="skip" href="#main">Skip to content</a>
<aside class="rail"><a class="brand" href="../index.html"><span class="mark">4D</span><span>FOURTH DOWN<small>NFL Line Lab</small></span></a>
<nav aria-label="Main"><a href="../index.html">Overview</a><a href="readiness.html" aria-current="page">Decision readiness</a>
<a href="requirements.html">Requirements</a><a href="decisions-critical.html">Decisions to make</a><a href="suggestions-board.html">Suggestions</a>
<a href="flagged.html">Flagged for review</a><a href="sources.html">Sources</a></nav>
<div class="railnote"><span class="dot"></span>Assessment snapshot <strong>{esc(payload['assessment_date'])}</strong><p>Clearance criteria are copied only from the registered gates. Missing numeric thresholds stay blank.</p></div>
<footer>Evidence first. Nothing inferred.</footer></aside>
<main id="main"><header class="top"><span>WORKSPACE <i>/ DECISION READINESS</i></span><span class="asof">{esc(len(payload['rows']))} TRACKED REQUIREMENTS</span></header>
<section class="pagetitle"><div class="eyebrow">REQUIREMENT GATES</div><h1>Decision readiness</h1>
<p>One row for every requirement currently in the assessed register. See the gate that blocks an unresolved item and the exact clearance rule where one is registered.</p></section>
<section class="content"><div class="statrow"><div class="stat"><strong>{counts.get('met', 0)}</strong><span>met</span></div><div class="stat"><strong>{counts.get('partly_met', 0)}</strong><span>partly met</span></div><div class="stat"><strong>{counts.get('open', 0)}</strong><span>open</span></div><div class="stat"><strong>{counts.get('in_progress', 0)}</strong><span>in progress</span></div></div>
<div class="note"><b>Coverage limitation:</b> {esc(payload['coverage_warning'])}<br><b>Threshold rule:</b> {esc(payload['threshold_policy'])}<br><b>Source rule:</b> Requirement/evidence links point to the owner brief and repository evidence. The assessment does not record a direct NFL source per requirement, so the NFL-source cell is deliberately flagged rather than guessed.<details><summary>Flagged cross-tree conflicts ({len(payload['cross_tree_conflicts'])})</summary><ul>{conflicts_html}</ul></details></div>
<div class="tablewrap"><table class="wide" data-table><caption>Requirement readiness — {esc(summary)}. Each row links to its assessment evidence and source brief.</caption><thead><tr><th>ID</th><th>Category</th><th>Requirement and assessment detail</th><th>Assessment</th><th>Blocking gate</th><th>Clearance criterion</th><th>Registered numeric threshold</th><th>Source links / flag</th></tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>
<p>Gate definitions: <a class="src-link" href="../data/gates.json">data/gates.json</a>. Requirement evidence registry: <a class="src-link" href="../data/audit/requirements_assessed.json">data/audit/requirements_assessed.json</a>. Official NFL sources actually used for NFL facts are listed on the <a href="sources.html">source registry</a>; no source has been inferred from a requirement's topic.</p>
</section></main></body></html>'''


def build(*, check: bool = False) -> None:
    payload = build_payload()
    json_bytes = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
    html_bytes = render(payload).encode()
    if check:
        failures = []
        for path, expected in ((OUT_JSON, json_bytes), (OUT_HTML, html_bytes)):
            if not path.exists() or path.read_bytes() != expected:
                failures.append(str(path.relative_to(ROOT)))
        if failures:
            raise SystemExit("readiness outputs stale: " + ", ".join(failures))
        print(f"readiness check passed: {payload['tracked_requirement_count']} rows; unregistered numeric thresholds remain blank")
        return
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_bytes(json_bytes)
    OUT_HTML.write_bytes(html_bytes)
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {OUT_HTML.relative_to(ROOT)} ({payload['tracked_requirement_count']} requirements)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if committed outputs differ from a fresh build")
    args = parser.parse_args()
    build(check=args.check)
