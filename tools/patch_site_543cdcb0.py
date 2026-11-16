#!/usr/bin/env python3
"""One-shot patch: wire the 2026-11-16 capture page and the shadow-baseline page into the site.

Run from the repository root. It inserts (a) two NAV entries, (b) the data loads, (c) two page
functions, (d) the two `write(...)` calls, and (e) one landing section — and then exits nonzero if any
anchor did not match, so it can never half-patch the generator.
"""
import io
import os
import re
import sys

P = "tools/build_site.py"
src = open(P, encoding="utf-8").read()


def sub(old, new, count=1):
    global src
    if src.count(old) != count:
        print(f"ABORT: anchor matched {src.count(old)} times, expected {count}:\n{old[:200]}")
        raise SystemExit(1)
    src = src.replace(old, new, count)


# ------------------------------------------------------------------ 1. NAV
sub('''    ("pages/readiness.html", "Decision readiness"),''',
    '''    ("pages/readiness.html", "Decision readiness"),
    # Added by session arena-543cdcb0-x1 (additive): the evidence layer the collector writes,
    # and the pre-registered model that scores against it.
    ("pages/capture-system.html", "Capture system"),
    ("pages/shadow-baseline.html", "Shadow baseline"),''')

# ------------------------------------------------------------------ 2. loads
sub('import csv\nimport html', 'import csv\nimport html\nimport io')
sub('''def load_audit(name):''', '''def cell_v(v):
    """A value inside an already-formatted cell, blank-rendered like `cell` does."""
    return esc(v) if str(v).strip() else "&mdash;"


def read_rows(path, delimiter=","):
    """A committed CSV/TSV as dicts, with `#` provenance lines stripped the way read_tsv does."""
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().split("\\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(io.StringIO("\\n".join(lines)), delimiter=delimiter))


def read_jsonl(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def load_audit(name):''')

sub('''STANDINGS_URL = "https://www.nfl.com/standings/division/2026/REG"''',
    '''# ------------------------------------------------- 2026-11-16 evidence layer (session 543cdcb0)
CAP_CFG = load_json("captures/config.json")
CAP_STATUS = load_json("captures/status.json")
CAP_INDEX = read_jsonl("data/captures/index.jsonl")
CAP_DIFFS = {}
for _fn in sorted(os.listdir(os.path.join(D, "captures", "diffs"))) if os.path.isdir(
        os.path.join(D, "captures", "diffs")) else []:
    if _fn.endswith(".csv"):
        CAP_DIFFS[_fn[:-4]] = read_rows(os.path.join("data", "captures", "diffs", _fn))

PREREG = load_json("preregistration/register.json")
SHADOW = load_json("shadow/backtest_summary.json")
SHADOW_SCORED = read_rows("data/shadow/games_scored.csv")
SHADOW_CAL = read_rows("data/shadow/calibration.csv")
SHADOW_FWD = read_rows("data/shadow/forecasts_pre_kickoff.csv")
PACK1616 = load_json("verification/2026_11_16/verification_summary_2026_11_16.json")
PROMO1616 = load_json("verification/2026_11_16/w10_promotion_2026_11_16.json")
STAND_DIFF = read_rows("data/verification/2026_11_16/standings_diff_2026_11_16.csv")
W10_FINALS = read_rows("data/verification/2026_11_16/official_w10_results_2026_11_16.tsv", "\\t")
W11_SLATE = read_rows("data/verification/2026_11_16/official_w11_schedule_2026_11_16.tsv", "\\t")
READ_1616 = "2026-11-16"
NFLCOM = "https://www.nfl.com/"

STANDINGS_URL = "https://www.nfl.com/standings/division/2026/REG"''')

# ------------------------------------------------------------------ 3. pages + main
sub('''# ---------------------------------------------------------------- exec summary''', '''# ---------------------------------------------------------------- capture system
def page_capture_system():
    """The evidence layer: what was read, when, with what hash, and whether it was shaped right."""
    fr = CAP_STATUS["freshness"]
    idx_rows = [[
        f'<td><b>{esc(e["dataset"])}</b></td>',
        cell(e["as_read_at"] or "not printed by the source"),
        str(e["rows"]),
        f'<td><span class="pill {"ok" if e["status"] == "new" else "muted-pill"}">{esc(e["status"])}</span></td>',
        f'<td><span class="pill {"ok" if e["drift"] == "pass" else "warn"}">{esc(e["drift"])}</span></td>',
        f'<td>{esc(e["content_sha256"][:16])}</td>',
        src_cell(e["sources"][0] if e["sources"] else repo_blob(e["payload"]),
                 "official page ↗"),
    ] for e in CAP_INDEX]

    fresh_rows = [[
        f'<td><b>{esc(d)}</b></td>',
        f'{v["captures"]} ({v.get("distinct_payloads", "?")} distinct)',
        cell(v["last_as_read_at"], "never captured"),
        cell(v["hours_since_last_read"], "unreadable"),
        f'{v["max_age_hours"]} h',
        f'<td><span class="pill {"ok" if v["status"] == "ok" else ("high" if v["status"] == "never-captured" else "warn")}">{esc(v["status"])}</span></td>',
        src_cell(repo_blob("data/captures/config.json"), "pin ↗"),
    ] for d, v in sorted(fr.items())]

    alarm_rows = []
    for a in CAP_STATUS["alarms"]:
        details = a["detail"] if isinstance(a["detail"], list) else [{"detail": a["detail"], "kind": a["kind"]}]
        for d in details:
            alarm_rows.append([
                f'<td><b>{esc(a["dataset"])}</b></td>',
                cell(d.get("kind", a["kind"])),
                f'<td>{esc(d["detail"])}</td>',
                cell(d.get("field")),
                cell(a["at"], "no clock printed"),
                src_cell(repo_blob("pipeline/drift.py"), "check ↗"),
            ]) or [[
        '<td colspan="3">No alarms: every retained read matched its pins.</td>',
        src_cell(repo_blob("data/captures/config.json"), "pins ↗"),
    ]]

    pin_rows = []
    for d, pin in sorted(CAP_CFG["pins"].items()):
        bits = []
        if "exact_rows" in pin:
            bits.append(f"exactly {pin['exact_rows']} rows")
        if "min_rows" in pin:
            bits.append(f"&ge; {pin['min_rows']} rows")
        if "max_rows" in pin:
            bits.append(f"&le; {pin['max_rows']} rows")
        if pin.get("required_fields"):
            bits.append(str(len(pin["required_fields"])) + " required fields")
        if pin.get("unique_key"):
            bits.append("unique on " + "+".join(pin["unique_key"]))
        if pin.get("invariants"):
            bits.append(" + ".join(pin["invariants"]))
        if pin.get("vocabulary"):
            bits.append("printed vocabulary on " + "/".join(pin["vocabulary"]))
        pin_rows.append([
            f'<td><b>{esc(d)}</b></td>',
            "; ".join(bits),
            cell(pin.get("why_game_status_allowance_is_high")
                 or pin.get("why_no_unique_key")
                 or CAP_CFG["freshness_note"]),
            src_cell(repo_blob("data/captures/config.json"), "config ↗"),
        ])

    diff_rows = []
    for name, rows in sorted(CAP_DIFFS.items()):
        kinds = {}
        for r in rows:
            kinds[r["change"]] = kinds.get(r["change"], 0) + 1
        a, b = name.split("__")[1:]
        diff_rows.append([
            f'<td><b>{esc(name)}</b></td>',
            f'{esc(a)} &rarr; {esc(b)}',
            str(len(rows)),
            ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())) or "none",
            "the surprise, not the level: a row that did not move is not repeated here",
            src_cell(repo_blob(f"data/captures/diffs/{name}.csv"), "diff ↗"),
        ])

    w10_rows = [[
        f'<td>{esc(r["game_id"])}</td>',
        cell(r["date_et"]),
        f'<td><b>{esc(r["away"])} {cell_v(r["away_score"])}</b> at <b>{esc(r["home"])} {cell_v(r["home_score"])}</b></td>',
        f'<td><span class="pill {"ok" if r["status"] == "Final" else "warn"}">{esc(r["status"])}</span></td>',
        cell(r["note"]),
        src_cell(r["source_url"], "Week 10 page ↗"),
    ] for r in W10_FINALS]

    w11_rows = [[
        f'<td>{esc(r["game_id"])}</td>',
        cell(f'{r["date_et"]} {r["time_et"]}'.strip()),
        f'<td>{esc(r["network"])}</td>',
        (f'<td><b>{esc(r["away"])} ({esc(r["away_record"])})</b> at <b>{esc(r["home"])} ({esc(r["home_record"])})</b></td>'
         if r["row_type"] == "game" else f'<td><b>{esc(r["away"])}</b> on bye ({esc(r["away_record"])})</td>'),
        cell(r["note"], "no label printed"),
        src_cell(r["source_url"], "Week 11 page ↗"),
    ] for r in W11_SLATE]

    checks = [[
        f'<td><b>{esc(k)}</b></td>',
        f'<td><span class="pill {PACK1616["checks"][k]["verdict"] == "pass" and "ok" or "high"}">{esc(PACK1616["checks"][k]["verdict"])}</span></td>',
        cell(PACK1616["checks"][k].get("note", "")),
        src_cell(repo_blob("tools/verify_2026_11_16.py"), "check code ↗"),
    ] for k in PACK1616["checks"]]

    promo_rows = [[
        f'<td>{esc(r["game_id"])}</td>',
        f'<td>{esc(r["away"])} {cell_v(r["away_score"])} at {esc(r["home"])} {cell_v(r["home_score"])}</td>',
        f'<td><span class="pill warn">{esc(r["status_published_2026_11_14"])}</span></td>',
        f'<td><span class="pill ok">{esc(r["status_official"])}</span></td>',
        cell(r["date_et"]),
        src_cell(r["source_url"], "official page ↗"),
    ] for r in PROMO1616["promoted_rows"]]

    body = f"""
<section class="pagetitle">
  <div class="eyebrow">EVIDENCE LAYER · READ {READ_1616}</div>
  <h1>The capture system: every official read, kept</h1>
  <p>The site used to publish <b>one</b> capture per dataset because the collector wrote
  <code>data/pipeline/&lt;dataset&gt;.json</code> and overwrote it on the next run &mdash; and because
  the collector's own commit step never actually pushed (see the box below). This page is the layer that
  fixes both: a dated, hash-addressed index of every read, with the drift pins that decide whether a
  read is publishable at all.</p>
</section>

<section class="content">
  <div class="statrow">
    {stat(len(CAP_INDEX), "captures retained", f"{len({e['content_sha256'] for e in CAP_INDEX})} distinct payloads")}
    {stat(len(fr), "datasets pinned", "freshness measured against the league's own publishing gap")}
    {stat(len(CAP_STATUS["alarms"]), "live alarms", "published, not silenced")}
    {stat(PACK1616["checks"]["A3_cross_page_records"]["records_compared"], "club records cross-checked", "three official pages, 0 mismatches")}
  </div>

  <div class="note"><b>What was broken, in its own log.</b> <code>_ci/commit.log</code> on
  <code>main</code> ends every scheduled run with
  <code>MARKER: PUSH FAILED after 5 attempts</code>. The commit step ran
  <code>rm -rf _ci</code> and <code>git reset --mixed</code>; <code>_ci/*.log</code> are <i>tracked</i>
  files (the comment beside the line claimed they were untracked), so two unstaged deletions were left in
  the tree, and <code>git rebase</code> refuses to run on a dirty tree. Every dataset the collector read
  was committed locally and thrown away, while the diagnostics log was pushed by the API &mdash; which is
  exactly the shape of <code>main</code>&rsquo;s last commit before this page existed. The job now restores
  those files, rebases with <code>--autostash</code>, pushes captures and derived artefacts as one unit,
  and fails loudly if it cannot land what it collected.
  <a href="{repo_blob("_ci/commit.log")}">the log ↗</a> ·
  <a href="{repo_blob(".github/workflows/data-refresh.yml")}">the workflow ↗</a></div>

  <h2>Captures retained, newest last</h2>
  {table(["Dataset", "Read at (clock time the page was read)", "Rows", "Payload", "Drift", "Content SHA-256 (first 16)", "Source"],
         idx_rows, "One line per read, from data/captures/index.jsonl", "wide", True)}
  <p class="muted"><b>New</b> means the content hash had not been seen before; <b>unchanged</b> means this
  run read the same page and got the same bytes. An unchanged day is recorded rather than skipped, because
  &ldquo;the report says nothing changed&rdquo; and &ldquo;nobody looked&rdquo; have to be distinguishable.</p>

  <h2>Freshness, against a budget the league can actually meet</h2>
  {table(["Dataset", "Captures", "Last read", "Hours since", "Budget", "Status", "Pin"], fresh_rows,
         "Freshness per dataset", "", True)}
  <p class="muted">{esc(CAP_CFG["freshness_note"])}</p>

  <h2>Alarms</h2>
  {table(["Dataset", "Kind", "What it means", "Field", "Read at", "Check"], alarm_rows, "Published alarms from data/captures/status.json", "", True)}
  <div class="note"><b>Gate versus alarm, and why the split is written down.</b> A violation whose kind is
  in <code>fail_the_build</code> stops a data publish (a missing field, a row count outside the pin, a
  duplicate key, a standings or slate that does not close). A violation in <code>alarm_only</code> is
  published next to the number that caused it. Both lists, and the reason for each placement, live in
  <a href="{repo_blob("data/captures/config.json")}"><code>data/captures/config.json</code></a>; the
  mutation test <code>python3 scripts/pipeline/verify_captures.py --self-test</code> proves all five pin
  classes can fail (5/5 caught on 2026-11-16).</div>

  <h2>The pins themselves</h2>
  {table(["Dataset", "What is pinned", "Why the pin is drawn where it is", "Config"], pin_rows,
         "Row counts, required fields, vocabularies and closures", "", True)}

  <h2>Deltas between consecutive reads &mdash; the surprise, not the level</h2>
  {table(["Capture pair", "From &rarr; to", "Changed cells", "By kind", "Reading", "Diff"], diff_rows,
         "Row-level deltas computed by the capture store", "wide", True)}
  <div class="note"><b>One trap this caught.</b> The first injury delta reported 14 players &ldquo;gone&rdquo;
  and 14 &ldquo;appeared&rdquo;. Nobody moved: the collector labels the Rams <code>LA</code>, the hand
  transcription labels them <code>LAR</code>. The payloads keep what each source printed and only the join
  normalises, so the spelling difference is visible instead of being silently repaired &mdash; and a new pin
  (<code>club-code-outside-register</code>) now reports it as an alarm on every read where it happens.</div>

  <h2>Week 10, as the official page printed it on {READ_1616}</h2>
  {table(["Game", "Date (ET)", "Line score", "Status", "Label printed by the page", "Source"], w10_rows,
         "13 finals + the Monday-night game, which had not been played at retrieval", "wide", True)}
  <p class="muted">Sixteen games&rsquo;-worth of record columns are printed on this page and on the standings
  page and on the Week 11 page; {PACK1616["checks"]["A3_cross_page_records"]["records_compared"]} of those
  records were compared across the three pages, {PACK1616["checks"]["A3_cross_page_records"]["mismatches"]} disagreed.</p>

  <h2>What moved since the published table</h2>
  {table(["Game", "Now printed", "Published 2026-11-14", f"Published {READ_1616}", "Date (ET)", "Source"], promo_rows,
         f"{PROMO1616['promoted_rows'].__len__()} rows promoted from scheduled to final; the published Week 10 table is left as the dated artefact it is", "wide", True)}
  <div class="note"><b>Standings: {len(STAND_DIFF)} field changes, all of them closing.</b> Applying the
  {PACK1616["checks"]["A5_dated_delta_closure"]["new_finals_applied"]} newly-final games to the published
  2026-11-14 table reproduces today&rsquo;s official W, L, T, PF and PA for all 32 clubs &mdash;
  {PACK1616["checks"]["A5_dated_delta_closure"]["assertions"]} assertions, 0 failures. The published table
  is <em>not</em> rewritten: the delta is the finding, dated on both ends
  (<a href="{repo_blob("data/verification/2026_11_16/standings_diff_2026_11_16.csv")}">the diff ↗</a>).</div>

  <h2>Week 11, the slate every forward forecast is made against</h2>
  {table(["Game", "Date + time (ET)", "Network", "Matchup (record as printed)", "Label printed by the page", "Source"], w11_rows,
         "13 fixtures + 6 clubs on bye = 32 clubs, which is the completeness invariant", "wide", True)}

  <h2>What this pack checked, and what it did not</h2>
  {table(["Check", "Verdict", "What it proves", "Code"], checks, "tools/verify_2026_11_16.py", "", True)}
  <div class="note"><b>Limits, stated by the tool that produced them.</b><ul>
  {''.join(f"<li>{esc(x)}</li>" for x in PACK1616["limits"])}
  </ul></div>

  <h2>What retention still does not do</h2>
  <ul>
    <li><b>No raw HTML bytes.</b> The reads on this page were taken with a page reader that returns parsed
    text, so the repository holds the transcription and its hash, not the document. The collector
    (which does fetch in CI) can store raw bytes beside each payload; that is a one-line change to
    <code>pipeline/run.py</code>, deliberately not made here because another session&rsquo;s open pull
    request owns that file. Request logged in
    <a href="{repo_blob("COORDINATION.md")}"><code>COORDINATION.md</code></a>.</li>
    <li><b>Two extraction paths, one series.</b> Until the collector runs green twice, a delta can mix a
    page change with an extractor difference. The pin set is what makes that visible rather than
    inferred; the fix is the series itself, which now exists.</li>
    <li><b>No snap counts, no inactives.</b> The brief&rsquo;s &ldquo;capture official inactive lists and
    snap counts&rdquo; item is still open: nothing in the retained set contains a snap share, so a
    backup replacing a starter remains confirmed only where the league prints a designation.</li>
  </ul>
</section>
"""
    return shell("Capture system", f"EVIDENCE LAYER · READ {READ_1616}", body, depth=1)


# ---------------------------------------------------------------- shadow baseline
def page_shadow():
    m = SHADOW["backtest"]
    boot = m["bootstrap"]
    luck = m["luck_panel"]
    reg_rows = [[
        f'<td><b>{esc(r["id"])}</b></td>',
        f'<td>{esc(r["name"])}</td>',
        f'<td><span class="pill {"ok" if r["state"] == "frozen" else "muted-pill"}">{esc(r["state"])}</span></td>',
        (f'<td><a href="https://github.com/karagemop466-tech/X1/commit/{esc(r["registration_commit"])}" '
         f'target="_blank" rel="noopener">{esc(r["registration_commit"][:10])} ↗</a><br>'
         f'<span class="muted">{esc(r["registered_at"])}</span></td>')
        if r["registration_commit"] else cell("", "not committed"),
        str(r["touches"]),
        cell(r["content_hash_matches_registration"]),
        src_cell(repo_blob(r["file"]), "rule text ↗"),
    ] for r in PREREG["rows"]]

    metric_rows = [
        ("games read from official pages", SHADOW["inputs"]["games"], "weeks 1-10, every row transcribed from an nfl.com page", "data/results/_raw/reads.tsv"),
        ("games scored", m["n_games"], f"weeks {int(SHADOW['frozen_constants']['warmup_weeks']) + 1}-10, each predicted only from strictly earlier games", "data/shadow/games_scored.csv"),
        ("Brier score", m["brier"], "lower is better; a proper score, so a hedge costs the forecaster rather than buying them", "data/shadow/backtest_summary.json"),
        ("Brier of the coin (0.5)", m["brier_coin_baseline"], "the floor any model has to beat", "data/shadow/backtest_summary.json"),
        ("Brier of the home baseline (0.55)", m["brier_home_baseline"], "the no-information forecast that already knows home teams win more often", "data/shadow/backtest_summary.json"),
        ("Brier skill vs home baseline", m["brier_skill_vs_home_baseline"], "benchmark-relative, not raw accuracy", "data/shadow/backtest_summary.json"),
        ("&hellip; game-cluster 95% lower bound", boot["skill_home_baseline_lower_bound"], f"{boot['resamples']:,} bootstrap resamples of whole games, seed {boot['seed']}; a point estimate is not a result", "data/shadow/backtest_summary.json"),
        ("Log-loss skill vs home baseline", m["log_skill_vs_home_baseline"], "the second proper score, so the ranking does not depend on one metric", "data/shadow/backtest_summary.json"),
        ("Hit rate on the model's side", m["hit_rate_model_side"], "printed beside the proper scores, never instead of them", "data/shadow/games_scored.csv"),
        ("Mean absolute error of the originable margin", m["mae_expected_margin_points"], "points; the fair line is this margin negated", "data/shadow/games_scored.csv"),
    ]
    mt = [[f'<td><b>{lbl}</b></td>', f'<td>{val if val != "" else "&mdash;"}</td>', cell(note),
           src_cell(repo_blob(path), "artefact ↗")] for lbl, val, note, path in metric_rows]

    cal_rows = [[f'<td>{esc(r["bin"])}</td>', str(r["n"]), cell(r["mean_p"]), cell(r["win_rate"]),
                 f'<td><span class="pill {"warn" if r["too_small_to_read"] == "yes" else "ok"}">{esc(r["too_small_to_read"])}</span></td>',
                 src_cell(repo_blob("data/shadow/calibration.csv"), "artefact ↗")] for r in SHADOW_CAL]

    fwd_rows = [[
        f'<td>{esc(r["week"])} · {esc(r["game_id"])}</td>',
        cell(r["kickoff_et"]),
        f'<td><b>{esc(r["away"])}</b> at <b>{esc(r["home"])}</b></td>',
        f'<td>{esc(r["p_home"])}</td>',
        f'<td><b>{esc(r["model_side"])}</b></td>',
        f'<td>{esc(r["fair_line_home"])}</td>',
        cell(r["market_line"], "no official price source (Q-02)"),
        cell(r["residual"], "blank while the market line is blank"),
        f'<td class="muted">{esc(r["recorded_at_utc"])}</td>',
        src_cell(r["source_url"], "official fixture ↗"),
    ] for r in SHADOW_FWD]

    blank_rows = [[f'<td><b>{esc(k)}</b></td>', cell(v), src_cell(repo_blob("docs/preregistration/PR-01-shadow-baseline.md"), "rule ↗")]
                  for k, v in SHADOW["blank_by_policy"].items()]

    game_rows = [[
        f'<td>{esc(r["week"])}</td>',
        cell(r["date"]),
        f'<td><b>{esc(r["away"])} ({esc(r["rating_away"])})</b> at <b>{esc(r["home"])} ({esc(r["rating_home"])})</b></td>',
        f'<td>{esc(r["away_score"])}&ndash;{esc(r["home_score"])}</td>',
        f'<td>{esc(r["p_home"])}</td>',
        f'<td>{esc(r["fair_line_home"])}</td>',
        f'<td>{esc(r["brier"])}</td>',
        f'<td>{esc(r["log_loss"])}</td>',
        src_cell(r["source_url"], "game ↗"),
    ] for r in SHADOW_SCORED]

    frozen = SHADOW["frozen_constants"]
    body = f"""
<section class="pagetitle">
  <div class="eyebrow">PR-01 · SINGLES-ONLY SHADOW BASELINE</div>
  <h1>The pre-registered baseline, scored with proper scores and uncertainty</h1>
  <p>This is the &ldquo;start with a singles-only shadow baseline&rdquo; requirement, run the way the brief
  demands it be run: one rule, frozen in a commit before it was scored, evaluated only on games predicted
  from games strictly earlier, judged by benchmark-relative Brier with a game-cluster interval, and
  <b>never</b> placed on the leaderboard. {esc(SHADOW["corpus"]["eligibility"])}</p>
</section>

<section class="content">
  <div class="statrow">
    {stat(m["n_games"], "games scored", "weeks 3-10 of 2026, chronological holdout")}
    {stat(f"{m['brier_skill_vs_home_baseline']:+.3f}", "Brier skill vs the 0.55 home baseline", "benchmark-relative, so raw accuracy cannot flatter it")}
    {stat(f"{boot['skill_home_baseline_lower_bound']:+.3f}", "95% lower bound", "the number a claim has to clear; it clears zero by a hair")}
    {stat(len(SHADOW_FWD), "games recorded pre-kickoff", SHADOW["forward"]["recorded_at_utc"])}
  </div>

  <div class="note"><b>Read the lower bound, not the point estimate.</b> Skill of
  {m['brier_skill_vs_home_baseline']:+.3f} with a 95% interval of
  [{boot['skill_home_baseline_lower_bound']:+.3f}, {boot['skill_home_baseline_ci'][1]:+.3f}] on
  {m['n_games']} games means the baseline is <em>probably</em> better than a no-information forecast and
  <em>only just</em> provably so. A single season of 117 games cannot support more than that sentence, and
  anything stronger on this page would be a fabrication. Multiplicity is disclosed:
  n_trials = {boot['n_trials']}, so the Bonferroni factor is {boot['bonferroni_alpha']} &mdash; which is
  honest only while nobody scores a second variant on this window without registering it first.</div>

  <h2>The three registered rules, and the commits that froze them</h2>
  {table(["ID", "Rule", "State", "Registration commit", "Touches", "Hash matches the registered text", "Rule file"],
         reg_rows, "data/preregistration/register.json", "wide", True)}
  <p class="muted">{esc(PREREG["rule"])} · {esc(PREREG["rows"][0]["verification_note"])} {esc(" ".join(PREREG["limits"]))}</p>

  <h2>Frozen constants, straight from the rule file</h2>
  <div class="note"><code>K = {frozen["K_prior_games"]} games</code> of prior weight;
  <code>H = {frozen["H_home_points"]} points</code> of home margin;
  <code>&sigma; = {frozen["SIGMA_points"]} points</code>; warm-up
  <code>{frozen["warmup_weeks"]} weeks</code>; benchmark
  <code>{frozen["home_baseline_p"]}</code>. {esc(frozen["note"])}</div>

  <h2>How it scored</h2>
  {table(["Measure", "Value", "What it means", "Artefact"], mt, "Walk-forward backtest, weeks 3-10", "wide", True)}

  <h2>The removal-of-luck panel</h2>
  <div class="note"><p>A bettor who always takes the model&rsquo;s side went
  <b>{luck["realised_wins_on_model_side"]}&ndash;{m["n_games"] - luck["realised_wins_on_model_side"]}</b> where
  its own probabilities expected <b>{luck["expected_wins_same_bets"]}</b> wins. The standard deviation of that
  difference is <b>{luck["sd_of_the_difference"]}</b> wins, so the gap is
  <b>{luck["z_luck_adjusted"]}</b> standard deviations &mdash; {esc(luck["reading"])}. Win totals are luck until
  they are compared with the sum of the probabilities behind them; that comparison is this panel, and it is
  the reason the leaderboard separates <em>signal</em> from <em>staking</em>.</p></div>

  <h2>Calibration &mdash; is a 65% game worth 65%?</h2>
  {table(["Probability bin (of the side picked)", "Games", "Mean predicted", "Realised win rate", "Readable?", "Artefact"],
         cal_rows, "Reliability in five bins, printed with the count in each", "", True)}

  <h2>What is blank here, and why that is the point</h2>
  {table(["Column", "Why it is blank", "Rule"], blank_rows, "Market line, residual, ROI, staking", "", True)}

  <h2>Pre-kickoff shadow record &mdash; written {esc(SHADOW["forward"]["recorded_at_utc"])}</h2>
  {table(["Week · Game", "Kickoff (ET)", "Matchup", "p(home)", "Model side", "Fair line (home)", "Market line", "Residual", "Recorded at", "Source"],
         fwd_rows, "14 games recorded before kickoff; immutable by build", "wide", True)}
  <p class="muted">{esc(SHADOW["forward"]["immutability"])} Fingerprint
  <code>{esc(SHADOW["forward"]["content_sha256"][:16])}&hellip;</code> ·
  <a href="{repo_blob("data/shadow/forecasts_pre_kickoff.csv")}">the file ↗</a></p>

  <h2>Every scored game</h2>
  {table(["Wk", "Date", "Matchup (rating)", "Score", "p(home)", "Fair line", "Brier", "Log loss", "Source"],
         game_rows, "One row per game, each with its official fixture page", "wide", True)}

  <div class="note"><b>Limits.</b><ul>
  {''.join(f"<li>{esc(x)}</li>" for x in SHADOW["limits"])}
  </ul></div>
</section>
"""
    return shell("Shadow baseline", "PR-01 · BACKTEST + PRE-KICKOFF RECORD", body, depth=1)


# ---------------------------------------------------------------- exec summary''')

# ------------------------------------------------------------------ 4. write calls
sub('''    write("pages/readiness.html", page_readiness())''',
    '''    write("pages/readiness.html", page_readiness())
    write("pages/capture-system.html", page_capture_system())
    write("pages/shadow-baseline.html", page_shadow())''')

# ------------------------------------------------------------------ 5. landing section
sub('''  <p class="muted">Full register, with every derivation, every note and the live 2026-11-15 re-verification:
  <a href="pages/readiness.html">decision readiness →</a> · generated by
  <code>tools/build_decision_readiness.py</code> from <code>data/readiness/decision_readiness.json</code>.</p>
</section>
"""''', '''  <p class="muted">Full register, with every derivation, every note and the live 2026-11-15 re-verification:
  <a href="pages/readiness.html">decision readiness →</a> · generated by
  <code>tools/build_decision_readiness.py</code> from <code>data/readiness/decision_readiness.json</code>.</p>
</section>

<section class="sectionhead"><div><div class="eyebrow">2026-11-16 · EVIDENCE AND BASELINE</div>
<h2>The collector was running green and publishing nothing &mdash; and what landed instead</h2></div>
<span class="tag">{len(CAP_INDEX)} CAPTURES · {len(STAND_DIFF)} STANDING CELLS MOVED · {SHADOW["backtest"]["n_games"]} GAMES SCORED</span></section>
<section class="content">
  <div class="statrow">
    {stat("13 / 14", "Week 10 games officially final", "the Monday-night game was still unplayed at read time", )}
    {stat(f"{len(PROMO1616['promoted_rows'])}", "rows promoted scheduled &rarr; final", "with both dates published, nothing overwritten")}
    {stat(PACK1616["checks"]["A5_dated_delta_closure"]["assertions"], "standings assertions", "0 failures: the delta closes exactly")}
    {stat(f"{SHADOW['backtest']['brier_skill_vs_home_baseline']:+.3f}", "baseline Brier skill", f"95% lower bound {SHADOW['backtest']['bootstrap']['skill_home_baseline_lower_bound']:+.3f} on 117 games")}
  </div>
  {table(["What happened", "Number", "Where to check it", "Source"], [
      ['<td><b>The scheduled collector never pushed its captures</b></td>', f'<td>{len(CAP_INDEX)} captures now retained</td>', '<td><a href="pages/capture-system.html">capture system &rarr;</a></td>', src_cell(repo_blob("_ci/commit.log"), "log ↗")],
      ['<td><b>Week 10 re-read from the official page</b></td>', f'<td>{len(W10_FINALS)} fixtures, {sum(1 for r in W10_FINALS if r["status"] == "Final")} final</td>', '<td><a href="pages/capture-system.html">Week 10 table &rarr;</a></td>', src_cell("https://www.nfl.com/schedules/2026/by-week/week-10", "nfl.com ↗")],
      ['<td><b>Standings re-read and diffed, not overwritten</b></td>', f'<td>{len(STAND_DIFF)} field changes, all closing</td>', '<td><a href="pages/capture-system.html">delta &rarr;</a></td>', src_cell("https://www.nfl.com/standings/league/2026/REG", "nfl.com ↗")],
      ['<td><b>Day-over-day injury movement, first time measured</b></td>', f'<td>{len(CAP_DIFFS.get("injuries__2026-11-14__2026-11-15", []))} changed cells</td>', '<td><a href="pages/capture-system.html">diff &rarr;</a></td>', src_cell(repo_blob("data/captures/diffs/injuries__2026-11-14__2026-11-15.csv"), "diff ↗")],
      ['<td><b>PR-01 shadow baseline registered and scored</b></td>', f'<td>skill {SHADOW["backtest"]["brier_skill_vs_home_baseline"]:+.3f}, n={SHADOW["backtest"]["n_games"]}</td>', '<td><a href="pages/shadow-baseline.html">shadow baseline &rarr;</a></td>', src_cell(repo_blob("docs/preregistration/PR-01-shadow-baseline.md"), "rule ↗")],
      ['<td><b>First pre-kickoff forecast record</b></td>', f'<td>{len(SHADOW_FWD)} games</td>', '<td><a href="pages/shadow-baseline.html">shadow record &rarr;</a></td>', src_cell(repo_blob("data/shadow/forecasts_pre_kickoff.csv"), "file ↗")],
    ], "The 2026-11-16 round, one row per claim", "wide", True)}
</section>
"""''')

open(P, "w", encoding="utf-8").write(src)
print("build_site.py patched")
