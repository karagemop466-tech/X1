"""Build a reproducible rules-only research page; no changes to model escrow."""
import argparse
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path

from regimes import REGIMES, may_declare
from trial import checked_record, history

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/kickoff-regimes/index.html'
AS_OF = date(2026, 11, 19)


def link(url, label):
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def table(headers, rows):
    return ('<div class="table-wrap"><table><thead><tr>' +
            ''.join(f'<th scope="col">{h}</th>' for h in headers) + '</tr></thead><tbody>' +
            '\n'.join('<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows) +
            '</tbody></table></div>')


def build():
    cohort = history()
    record = checked_record()
    forecasts = []
    for r in record['forecasts']:
        forecasts.append([escape(r['away'] + ' at ' + r['home']), r['threshold'],
                          *[f'{p:.1%}' for p in r['candidate']], f"{r['benchmark'][2]:.1%}",
                          link(r['official_game'], 'NFL Game Centre')])
    weeks = Counter(int(r['week']) for r in cohort)
    rules, late = [], []
    for year, rule in REGIMES.items():
        cite = link(rule.declaration_source, 'NFL declaration rule')
        rules.append([year, rule.declaration_source_date, rule.kickoff_note, cite + ' · ' + link(rule.kickoff_source, 'Kickoff details')])
        states = [(1, -1), (4, -1), (4, 0), (4, 1)]
        late.append([year, *['Permitted' if may_declare(year, q, margin) else 'Not permitted' for q, margin in states], cite])
    counts = [[week, weeks[week], link(f'https://www.nfl.com/schedules/2026/by-week/week-{week}', 'NFL weekly results')]
              for week in sorted(weeks)]
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kickoff rules and comparable games · NFL line research</title><link rel="stylesheet" href="../assets/styles.css"></head>
<body><main class="wrap"><nav>{link('../../index.html','Dashboard')} · {link('../index.html','Research')} · {link('../../pages/flagged.html','Flagged for review')}</nav>
<h1>Which kickoffs are comparable?</h1>
<p class="lede">Use the rules in force for the game, not the rules in force today. In regulation, a tied team could not declare an onside kick in 2025; it can in 2026. Permission is not a prediction that the team will try it.</p>
<p>Rule audit: {AS_OF.isoformat()}. This supplements the research lab’s 2026-11-14 snapshot. <b>Decision: separate the seasons in research; leave live prices unchanged.</b></p>
<h2>Week 11 · paper totals trial</h2>
<p><b>Can team context improve on the league distribution?</b> KR-T1 assigns twice the weight to past games involving either club. The control counts every eligible final once. Both forecast the full-game total against PR-04’s frozen league threshold, not against a sportsbook. No licensed quote: market line and residual are withheld.</p>
<p>Registered before evaluation · {link('https://github.com/karagemop466-tech/X1/blob/' + record['registered_commit'] + '/research/kickoff-regimes/KR-T1.md','Frozen rule and two-sided gates')} · Recorded {record['recorded_at_utc']} · {link('week11.json','Exact probabilities, inputs and source hashes')}. These forecasts are model estimates, not official NFL numbers.</p>
{table(['Game','Threshold (pts)','Under','Push','Over','Control: over','Fixture'],forecasts)}
<p>At recording: 0 of 13 results available. The {link('https://github.com/karagemop466-tech/X1/actions/workflows/paper-totals-settlement.yml','automatic settlement report')} updates when the verified feed changes. No skill estimate until all games have official finals. Even a positive paired Brier improvement with its entire 95% interval above zero would justify only another paper trial.</p>
<h2>Three distinct regular-season rule sets</h2>
{table(['NFL season','Declaration source date','Kickoff context (not every exception)','Official evidence'],rules)}
<h2>Can the kicking team declare?</h2>
<p>Examples assume a kickoff opportunity and refer to the kicking team’s score immediately before the kick. Overtime, unknown states and other seasons are outside this filter. Nothing here identifies an actual attempt.</p>
{table(['Season','Q1 · trailing','Q4 · trailing','Q4 · tied','Q4 · leading','Official evidence'],late)}
<h2>Which finals qualify as context for a 2026 total?</h2>
<p><b>{len(cohort)} regular-season finals</b> in the verified results store have a matching rule set and a retrieval date strictly before {AS_OF}. Same-day reads are excluded because their timestamps have only day precision. These are game counts, not counts of kickoffs or declarations.</p>
{table(['Week','Comparable finals (n)','Official evidence'],counts)}
<h2 id="review">Flagged for review · what would change the decision?</h2>
<p><b>Unknown: recovery probability, change in total points and change in comeback probability.</b> The frozen PR-04 total B field named <code>our_probability</code> carries a difference in points, not a probability. KR-T1 does not use it. Final scores cannot identify a kick, the pre-kick score or its outcome. No replacement probability, fixed points penalty or strategy reward is published.</p>
<ol><li>Can we measure how often a team declares? First verify a rights-cleared official play-level source with all opportunities, including ordinary kicks. A log of successful recoveries alone gives the wrong denominator.</li>
<li>Does the filter improve predictions? Freeze the rule, benchmark, window and trial count before the next evaluation. Compare otherwise identical models on the same chronological holdout; report game-cluster uncertainty and sample size.</li>
<li>Retain a new feature only if prospective improvement clears the registered gate. If the gain disappears or evidence is incomplete, keep the existing baseline and the candidate in paper testing.</li></ol>
<p>Source for rule scope: {link(REGIMES[2026].kickoff_source,'2026 NFL Rulebook, Rule 6')}. The research gates are project policy, not NFL findings.</p>
</main></body></html>\n'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    page = build()
    if args.check:
        if not OUT.is_file() or page != OUT.read_text():
            raise SystemExit(f'Stale: {OUT.name}; run {__file__}')
    else:
        OUT.write_text(page)
