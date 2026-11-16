#!/usr/bin/env python3
"""One-shot patch (part 2): the "Suggestions & open questions" page.

Same discipline as patch_site_543cdcb0.py — every anchor must match exactly once or the script aborts
before writing, so the generator is never left half-patched.
"""
import sys

P = "tools/build_site.py"
src = open(P, encoding="utf-8").read()


def sub(old, new, count=1):
    global src
    if src.count(old) != count:
        print(f"ABORT: anchor matched {src.count(old)} times, expected {count}:\n{old[:160]}")
        raise SystemExit(1)
    src = src.replace(old, new, count)


sub('''    ("pages/shadow-baseline.html", "Shadow baseline"),''',
    '''    ("pages/shadow-baseline.html", "Shadow baseline"),
    ("pages/next-decisions.html", "Suggestions & questions"),''')

sub('''PACK1616 = load_json("verification/2026_11_16/verification_summary_2026_11_16.json")''',
    '''NEXT = load_json("next_decisions/round_2026_11_16.json")
PACK1616 = load_json("verification/2026_11_16/verification_summary_2026_11_16.json")''')

sub('''# ---------------------------------------------------------------- exec summary''',
    '''# ---------------------------------------------------------------- next decisions
def page_next_decisions():
    """The review board: suggestions with paths to choose between, and the questions each decision needs."""
    sug_rows = [[
        f'<td><b>{esc(s["id"])}</b></td>',
        cell(s["area"]),
        f'<td><b>{esc(s["title"])}</b></td>',
        f'<td>{esc(s["why"])}</td>',
        f'<td><b>A</b> &mdash; {esc(s["path_a"][3:] if s["path_a"].startswith("A: ") else s["path_a"])}<br>'
        f'<b>B</b> &mdash; {esc(s["path_b"][3:] if s["path_b"].startswith("B: ") else s["path_b"])}<br>'
        f'<b>C</b> &mdash; {esc(s["path_c"][3:] if s["path_c"].startswith("C: ") else s["path_c"])}<br>'
        f'<span class="pill ok">recommended {esc(s["recommended"])}</span> {esc(s["recommended_because"])}</td>',
        f'<td>{esc(s["impact"])} / {esc(s["effort"])} / {esc(s["risk"])}</td>',
        cell(s["decision_status"]),
        src_cell(repo_blob(s["evidence_file"]), "evidence ↗"),
    ] for s in NEXT["suggestions"]]

    q_rows = [[
        f'<td><b>{esc(q["id"])}</b></td>',
        f'<td><b>{esc(q["question"])}</b></td>',
        f'<td>{esc(q["known"])}</td>',
        f'<td>{esc(q["missing"])}</td>',
        f'<td>{esc(q["how_to_find_out"])}</td>',
        f'<td>{esc(q["unblocks"])}</td>',
        f'<td>{esc(q["blocking"])}</td>',
        cell(q["default_if_unanswered"]),
        src_cell(q["source_url"], "source ↗"),
    ] for q in NEXT["questions"]]

    exec_rows = [[f'<td><b>{esc(x["what"])}</b></td>', f'<td>{esc(x["detail"])}</td>',
                  src_cell(repo_blob("data/next_decisions/round_2026_11_16.json"), "register ↗")]
                 for x in NEXT["executive_summary"]]

    blocked = sum(1 for q in NEXT["questions"] if q["default_if_unanswered"])
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">REVIEW BOARD · READ {READ_1616}</div>
  <h1>Suggestions and open questions, before anything is implemented</h1>
  <p>Two lists, kept apart on purpose. The first is what this session would change on the site to make
  decisions easier, with the alternative paths spelled out and a recommendation that is <em>advice, not a
  decision</em>. The second is what has to be known &mdash; or admitted as unknowable &mdash; before a
  decision on those items would be reasonable rather than lucky. Nothing here is implemented by the tool
  that writes it, and no row can mark itself accepted: <code>decision_status</code> changes only when a
  human commits a change to it.</p>
</section>

<section class="content">
  <div class="statrow">
    {stat(len(NEXT["suggestions"]), "suggestions with three paths each", "impact / effort / risk stated per row")}
    {stat(len(NEXT["questions"]), "questions blocking a decision", f"{blocked} have a stated default while unanswered")}
    {stat(len(NEXT["executive_summary"]), "things worth knowing this round", "each one points at its register")}
    {stat(sum(1 for s in NEXT["suggestions"] if s["risk"] == "Low"), "low-risk items", "the cheapest to say yes to")}
  </div>
  <div class="note"><b>{esc(NEXT["rule"])}</b> {esc(NEXT["impact_effort_note"])}</div>

  <h2>Executive summary &mdash; the details that change how to read the site</h2>
  {table(["What changed this round", "The detail", "Register"], exec_rows,
         "Five facts, each checkable in the file it names", "wide", True)}

  <h2>Suggestions for the site, with the paths to choose between</h2>
  {table(["ID", "Area", "Suggestion", "Why it is on this list", "Paths, and the recommendation",
          "Impact / effort / risk", "Decision status", "Evidence"], sug_rows,
         "Every row is the product of something measured this round, not a general principle", "wide", True)}

  <h2>Questions to answer first, with what we already know</h2>
  {table(["ID", "Question", "What the repository already establishes", "What is missing",
          "How to find out", "What it unblocks", "What it keeps blank meanwhile",
          "Default if unanswered", "Source"], q_rows,
         "Known / missing / how to discover / what it gates &mdash; one row per decision", "wide", True)}
  <p class="muted">Rows are deliberately not merged with the 20-row suggestion register the collector
  generates (<a href="suggestions.html">suggestions →</a>,
  <a href="suggestions-board.html">board →</a>): that one is a scan of the whole brief and is rewritten on
  each collection, while this one is a dated review of a single round. Where they overlap &mdash; the price
  source, the bankroll, the reward rules &mdash; this page repeats the question only to name what the last
  week of work changed about it.</p>

  <div class="note"><b>How to use this page.</b> Answer in the register, not in chat: change
  <code>decision_status</code> (and, where a question was decided, the text of
  <code>default_if_unanswered</code>) in
  <a href="{repo_blob("data/pipeline/suggestions.json")}"><code>data/pipeline/suggestions.json</code></a>-style
  rows in <code>tools/build_next_decisions.py</code>, and the gate <code>--check</code> keeps the committed
  register honest. Nine of the ten suggestions are implementable without waiting; the tenth (S-22) is
  blocked on Q-62, which is a one-line policy decision.</div>
</section>
"""
    return shell("Suggestions & questions", f"REVIEW BOARD · READ {READ_1616}", body, depth=1)


# ---------------------------------------------------------------- exec summary''')

sub('''    write("pages/shadow-baseline.html", page_shadow())''',
    '''    write("pages/shadow-baseline.html", page_shadow())
    write("pages/next-decisions.html", page_next_decisions())''')

sub('''      ['<td><b>First pre-kickoff forecast record</b></td>', f'<td>{len(SHADOW_FWD)} games</td>', '<td><a href="pages/shadow-baseline.html">shadow record &rarr;</a></td>', src_cell(repo_blob("data/shadow/forecasts_pre_kickoff.csv"), "file ↗")],''',
    '''      ['<td><b>First pre-kickoff forecast record</b></td>', f'<td>{len(SHADOW_FWD)} games</td>', '<td><a href="pages/shadow-baseline.html">shadow record &rarr;</a></td>', src_cell(repo_blob("data/shadow/forecasts_pre_kickoff.csv"), "file ↗")],
      ['<td><b>A review board so the next round is chosen, not guessed</b></td>', f'<td>{len(NEXT["suggestions"])} suggestions · {len(NEXT["questions"])} questions</td>', '<td><a href="pages/next-decisions.html">suggestions &amp; questions &rarr;</a></td>', src_cell(repo_blob("data/next_decisions/round_2026_11_16.json"), "register ↗")],''')

open(P, "w", encoding="utf-8").write(src)
print("build_site.py patched (next-decisions page)")
