import unittest
from tools.designation_calibration import evaluate


class Calibration(unittest.TestCase):
    def test_point_in_time_and_missingness(self):
        r = dict(season='test', game_id='1', team_id='T', player_id='A', source='https://www.nfl.com/test',
                 kickoff='2026-11-19T15:00Z', captured_at='2026-11-19T12:00Z', designation='Questionable')
        rows = [r, dict(r, player_id='B'), dict(r, player_id='C'), dict(r, designation='Out', captured_at=r['kickoff'])]
        result, = evaluate(rows, [dict(r, game_book_status='played'), dict(r, player_id='B', game_book_status='active_dnp')])
        self.assertEqual((result['n'], result['play_rate'], result['unmatched']), (2, .5, 1))
        self.assertAlmostEqual(result['wilson95'][0], .09453, places=4)
        with self.assertRaises(ValueError):
            evaluate(rows+[r], [])
        self.assertEqual(evaluate([r, dict(r, captured_at='2026-11-19T14:00Z', designation='')], []), [])
