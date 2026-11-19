#!/usr/bin/env python3
"""Render the canonical decision-center section from data/suggestions/*.json.

Run `python3 tools/build_decision_center.py` to write suggestions/*.html.
Run `python3 tools/build_decision_center.py --check` to fail if the committed
pages are stale. No NFL value is entered here: every displayed value comes from
the register, which carries a source link on every row.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "suggestions"
OUT = ROOT / "suggestions"
SNAP = "2026-11-14"          # required by the site's snapshot-date contract
BUILT = "2026-11-19"

PAGES = [
    ("index.html", "Overview"),
    ("questions.html", "Questions & answers"),
    ("paths.html", "Choose a path"),
    ("missing.html", "Discover missing information"),
    ("review.html", "Review log & flags"),
]


def e(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def src(url: str, label: str = "source") -> str:
    return (f'<a class="src-link" href="{e(url)}" target="_blank" rel="noopener" '
            f'title="{e(url)}">{e(label)}</a>')


def shell(title: str, eyebrow: str, lede: str, body: str, active: str) -> str:
    nav = "".join(
        f'<a class="{"active" if name == active else ""}" href="{name}">{e(label)}</a>'
        for name, label in PAGES
    )
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} — X1 Decision Center</title>
<meta name="description" content="X1 decision center: reviewed suggestions, questions and the information needed before a decision. Every row carries a source link.">
<link rel="stylesheet" href="../assets/site.css">
</head>
<body>
<div class="rail">
  <a class="brand" href="../index.html"><span class="mark">X1</span><span>Decision Center</span></a>
  <nav>{nav}<a href="../pages/flagged.html">Flagged for review</a><a href="../console/index.html">Line console</a><a href="../hub/index.html">Second opinion</a></nav>
  <div class="railnote">Snapshot {SNAP} · register built {BUILT}<br>Nothing here is implemented from a suggestion.</div>
</div>
<div class="content">
  <div class="top"><div class="eyebrow">{e(eyebrow)}</div><h1>{e(title)}</h1><p class="lede">{e(lede)}</p></div>
{body}
  <div class="mainfoot">Built by <code>tools/build_decision_center.py</code> from
  <code>data/suggestions/decision_center.json</code> and <code>official_reads.json</code> on {BUILT}.
  Repository records are labelled as such and are never presented as NFL facts. Values that cannot
  be confirmed from a source are left blank and listed as unverified.</div>
</div>
</body>
</html>
'''


def table(headers: list[str], rows: list[list[str]], caption: str = "") -> str:
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    cap = f"<h2>{e(caption)}</h2>" if caption else ""
    return f'{cap}<div class="tablewrap"><table data-table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def note(text: str) -> str:
    return f'<div class="note">{e(text)}</div>'


def load():
    reg = json.loads((DATA / "decision_center.json").read_text(encoding="utf-8"))
    reads = json.loads((DATA / "official_reads.json").read_text(encoding="utf-8"))
    return reg, reads


def build() -> dict[str, str]:
    reg, reads = load()
    q, s, m = reg["questions"], reg["suggestions"], reg["missing_information"]
    boards, flags = reg["source_boards"], reg["flags"]
    pages: dict[str, str] = {}

    stats = [
        ("questions", len(q), "held, missing, answer, next step"),
        ("paths", len(s), "all proposed, none implemented here"),
        ("missing inputs", len(m), "each with a source candidate"),
        ("boards reconciled", len(boards), "different IDs, one review surface"),
        ("flags", len(flags), "non-blocking, for manual review"),
        ("official reads", len(reads["reads"]), "re-read 2026-11-19"),
    ]
    stat_html = '<div class="statrow">' + "".join(
        f'<div class="stat"><div class="big">{e(n)}</div><div>{e(label)}</div>'
        f'<div class="statnote">{e(sub)}</div></div>' for label, n, sub in stats
    ) + '</div>'

    index_body = f'''
{note("Decision rule: this section reconciles existing registers and shows the paths. It does not choose a path, implement a suggestion, or publish an unsourced value. Every owner-decision cell is blank and marked unverified until the owner fills it in.")}
{stat_html}
<div class="cards">
<div class="card"><h3>Questions &amp; answers</h3><p>What we know, what we do not know, the answer that is possible today, and how to discover the rest.</p><p><a class="btn" href="questions.html">Read the {len(q)} questions</a></p></div>
<div class="card"><h3>Choose a path</h3><p>{len(s)} reconciled suggestions, each with three paths, a recommendation, a cost and an explicit blank decision cell.</p><p><a class="btn" href="paths.html">Review the paths</a></p></div>
<div class="card"><h3>Discover missing information</h3><p>{len(m)} inputs that block a decision, with the official source candidate and the collection step.</p><p><a class="btn" href="missing.html">See the gaps</a></p></div>
<div class="card"><h3>Review log &amp; flags</h3><p>Where each row came from, the {len(flags)} source irregularities found on 2026-11-19, and the five official pages re-read.</p><p><a class="btn" href="review.html">Open the review log</a></p></div>
</div>
<h2>Start with these five decisions</h2>
''' + table(
        ["ID", "Decision", "Why it is first", "Recommended path", "Source"],
        [[e(r["id"]), e(r["title"]), e(r["why"]), e(r["recommended"]), src(r["source_url"], "source")]
         for r in s[:5]],
    ) + f'''
<h2>How to use this section</h2>
<div class="cards">
<div class="card"><h3>1. Read the question</h3><p>Each row states the information held and the information missing. A row marked BLOCKED has no answer that the current evidence can support.</p></div>
<div class="card"><h3>2. Compare paths</h3><p>The paths page keeps A, B and C separate with impact, effort, risk and what each unlocks. The recommendation is a reading aid, not a decision.</p></div>
<div class="card"><h3>3. Record the choice</h3><p>Write the chosen path in the blank Decision and Owner cells in <code>data/suggestions/decision_center.json</code>, then rebuild. Until then the site shows UNVERIFIED / AWAITING OWNER.</p></div>
<div class="card"><h3>4. Only then implement</h3><p>No path is implemented by this section. The one exception is the review surface itself, which the owner explicitly asked for.</p></div>
</div>
'''
    pages["index.html"] = shell("Decision Center", "Overview",
        "One place to decide what to build next: the questions, the evidence we hold, the evidence we do not, and the paths available.",
        index_body, "index.html")

    q_body = note("Every answer below is limited to what an official NFL page actually printed or to a repository record that is labelled as such. Computed numbers from third-party mirrors are not republished here as facts; see the review log and the flagged page.") + table(
        ["ID", "Area", "Question", "Information held", "Information missing", "Answer", "Status", "How to discover", "Blocks", "Source"],
        [[e(r["id"]), e(r["area"]), e(r["question"]), e(r["information_held"]),
          e(r["information_missing"]), e(r["answer"]), e(r["status"]),
          e(r["how_to_discover"]), e(r["blocks"]), src(r["source_url"], r["source_note"].split(":")[0])]
         for r in q],
    )
    pages["questions.html"] = shell("Questions, information and answers", "Decisions / evidence",
        "A question is answerable only when the information it needs exists. Where it does not, the row says so and names the missing input.",
        q_body, "questions.html")

    paths_body = note("All rows are proposed and awaiting an owner decision. The Decision and Owner cells are deliberately blank: UNVERIFIED / AWAITING OWNER is a status, not a value.") + table(
        ["ID", "Area", "Suggestion", "Problem", "Path A", "Path B", "Path C", "Recommended", "Why", "Impact", "Effort", "Risk", "Unlocks", "Decision", "Owner", "Source"],
        [[e(r["id"]), e(r["area"]), e(r["title"]), e(r["problem"]), e(r["path_a"]),
          e(r["path_b"]), e(r["path_c"]), e(r["recommended"]), e(r["why"]), e(r["impact"]),
          e(r["effort"]), e(r["risk"]), e(r["unlocks"]),
          '<span class="warn">UNVERIFIED / AWAITING OWNER</span>' if not r["decision"] else e(r["decision"]),
          e(r["owner"]) if r["owner"] else "", src(r["source_url"], "source")]
         for r in s],
    )
    pages["paths.html"] = shell("Choose a path", "Decisions / suggestions",
        "One reconciled list of choices, with cost, risk and what each path unlocks. Nothing here is implemented until a path is selected.",
        paths_body, "paths.html")

    miss_body = note("These are gaps, not values. No blank has been filled with an estimate; each row names the source candidate that would settle it.") + table(
        ["ID", "Missing information", "Why it is missing", "Official source candidate", "How to collect", "Clears", "State", "Source"],
        [[e(r["id"]), e(r["missing_information"]), e(r["why_it_is_missing"]),
          e(r["official_source_candidate"]), e(r["how_to_collect"]), e(r["clears"]),
          e(r["current_state"]), src(r["source_url"], "source")] for r in m],
    )
    pages["missing.html"] = shell("Discover missing information", "Decisions / gaps",
        "The inputs that must exist before a decision can be made, and the source that could supply each one.",
        miss_body, "missing.html")

    review_body = note("Sources are of two kinds: official NFL pages re-read on 2026-11-19, and repository records linked through github.com. A repository record is never an NFL fact.") + table(
        ["ID", "Official page re-read", "Title as returned", "What was observed", "Irregularity", "Used by", "Source"],
        [[e(r["id"]), e(r["url"].split("/")[2]), e(r["page_title_returned"]), e(r["observed"]),
          e(r["irregularity"]), e(r["used_by"]), src(r["url"], "official page")] for r in reads["reads"]],
        "Official reads, 2026-11-19",
    ) + table(
        ["Board", "Path", "Rows", "Scope", "Source"],
        [[e(b["id"]), e(b["path"]), e(b["rows"]), e(b["scope"]), src(b["url"], "board")] for b in boards],
        "Reconciled source boards",
    ) + table(
        ["ID", "Flag", "What is verified", "What is unknown", "What settles it", "Blocks release", "Source"],
        [[e(f["id"]), e(f["item"]), e(f["verified"]), e(f["unknown"]), e(f["settles_it"]),
          e("no" if not f["blocks_release"] else "yes"), src(f["source_url"], "source")] for f in flags],
        "Flagged for review (non-blocking)",
    ) + f'''
<h2>Decision sequence</h2>
<div class="cards">
<div class="card"><h3>First</h3><p>Ratify one canonical board (DS-12). Seven boards currently disagree on IDs and counts.</p></div>
<div class="card"><h3>Then</h3><p>Decide the price-data policy (DS-01) and the results coverage (DS-02). Those two gates decide whether any scored claim is possible.</p></div>
<div class="card"><h3>Then</h3><p>Resolve rights and participation (DS-03, DS-14) before building any personnel feature.</p></div>
<div class="card"><h3>Last</h3><p>Only after those gates, choose model, scoring and site features from the remaining paths.</p></div>
</div>
'''
    pages["review.html"] = shell("Review log and flags", "Decisions / provenance",
        "Where every row came from, what was re-read live, and the source irregularities that are published rather than silently corrected.",
        review_body, "review.html")
    return pages


def main() -> int:
    pages = build()
    check_only = "--check" in sys.argv
    problems = []
    for name, text in pages.items():
        path = OUT / name
        if check_only:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                problems.append(f"stale or missing: suggestions/{name}")
        else:
            path.write_text(text, encoding="utf-8")
    if problems:
        print("Decision center --check FAILED:")
        for p in problems:
            print(" -", p)
        return 1
    print(f"Decision center: {len(pages)} pages, "
          f"{len(json.loads((DATA / 'decision_center.json').read_text())['questions'])} questions, "
          f"{len(json.loads((DATA / 'decision_center.json').read_text())['suggestions'])} paths "
          f"({'checked' if check_only else 'written'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
