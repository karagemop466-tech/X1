import unittest
from datetime import date

from regimes import may_declare, prior_finals
from trial import checked_record, distribution, evaluate, forecast, history


class TrialTests(unittest.TestCase):
    def test_regulation_rules(self):
        for year, early_trailing, late_tied in ((2024, False, False), (2025, True, False), (2026, True, True)):
            self.assertEqual(may_declare(year, 1, -1), early_trailing)
            self.assertTrue(may_declare(year, 4, -1))
            self.assertEqual(may_declare(year, 4, 0), late_tied)
            self.assertEqual(may_declare(year, 4, 1), late_tied)
        for args in [(2027, 4, -1), (2024, 5, -1), (2026, True, 1), (2026, 1, None)]:
            self.assertIsNone(may_declare(*args))

    def test_prior_reads_only(self):
        row = history()[0]
        cutoff = date.fromisoformat(row['retrieved_at'])
        self.assertEqual(prior_finals([row], 2026, cutoff), [])
        self.assertEqual(prior_finals([row], 2025, date(2026, 11, 19)), [])
        for rows in ([row, row], [dict(row, retrieved_at='2000-01-01')], [dict(row, game_url='https://example.org')]):
            with self.assertRaises(ValueError):
                prior_finals(rows, 2026, date(2026, 11, 19))

    def test_distribution(self):
        self.assertEqual(distribution([1, 0, 1], 46.5), [.5, 0, .5])
        self.assertEqual(distribution([1, 1, 1], 46.), [1/3]*3)
        game = dict(home_team='ARI', away_team='LA', home_score='30', away_score='16')
        fixture = dict(our_fair_line='46', away='LAR', home='AZ', game_id='', kickoff_utc='', official_fixture_url='')
        self.assertEqual(forecast([game], fixture)['weighted_counts'], [0, 2, 0])

    def test_freeze_and_score_gate(self):
        rows = checked_record()['forecasts']
        for r in rows:
            for k in ('benchmark', 'candidate'):
                self.assertAlmostEqual(sum(r[k]), 1)
                self.assertTrue(all(0 <= p <= 1 for p in r[k]))
        # Synthetic finals exercise the settlement path only, never written or published.
        finals = [dict(game_url=r['official_game'], away_team=r['away'], home_team=r['home'],
                       source_url='https://www.nfl.com/schedules/2026/by-week/week-11',
                       away_score='20', home_score='26') for r in rows]
        self.assertEqual(evaluate(rows, finals[:-1])['status'], 'pending')
        with self.assertRaises(ValueError):
            evaluate(rows, finals + finals[:1])
        result = evaluate(rows, finals)
        self.assertEqual(result['n'], 13)
        self.assertAlmostEqual(result['improvement'], result['benchmark_brier'] - result['candidate_brier'])


if __name__ == '__main__':
    unittest.main()
