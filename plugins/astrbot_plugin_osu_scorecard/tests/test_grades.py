"""Regression coverage for failed recent score 7618912197 and mania grades."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from card import build_card
from map_combo import parse_bpm_range


class GradeTests(unittest.TestCase):
    def test_variable_bpm_uses_uninherited_timing_points(self):
        osu = "[TimingPoints]\n0,705.8823529411765,4,2,0,100,1,0\n1,-50,4,2,0,100,0,0\n2,189.2744479495268,4,2,0,100,1,0\n[HitObjects]\n"
        bpm_range = parse_bpm_range(osu)
        self.assertEqual(tuple(round(v) for v in bpm_range), (85, 317))
        card = build_card({}, {'bpm': 214}, {}, bpm_range=bpm_range)
        self.assertEqual(card.bpm, '85–317')
        self.assertEqual(build_card({}, {'bpm': 214}, {}).bpm, '214')

    def grade(self, **score):
        return build_card(score, {}, {}).grade

    def test_real_failed_recent_score(self):
        score = dict(rank='F', passed=False, accuracy=0.469151, ruleset_id=3,
                     statistics=dict(ok=9, meh=5, good=11, miss=15, great=11, perfect=4))
        data = build_card(score, {}, {})
        self.assertEqual(data.accuracy, '46.91%')
        self.assertEqual(data.accuracy_lazer, '47.57%')
        self.assertEqual(data.other_accuracy_label, 'STABLE ACC')
        self.assertEqual(data.grade, 'F')
        # Same judgements without a failure or API grade must be D, not C.
        self.assertEqual(self.grade(statistics=score['statistics']), 'D')

    def test_custom_speed_and_client_label(self):
        score = {'id': 7625801262, 'mods': [
            {'acronym': 'DT', 'settings': {'speed_change': 1.27}}],
            'legacy_score_id': None, 'rank': 'S'}
        data = build_card(score, {}, {})
        self.assertEqual(data.to_layers()['mod_1_mult'], 'x1.27')
        self.assertEqual(data.server_tag, 'Lazer')
        stable = build_card({'mods': ['DT'], 'legacy_score_id': 123}, {}, {})
        self.assertEqual(stable.to_layers()['mod_1_mult'], 'x1.5')
        self.assertEqual(stable.server_tag, 'Stable')
        ht = build_card({'mods': [{'acronym': 'HT'}]}, {}, {})
        self.assertEqual(ht.to_layers()['mod_1_mult'], 'x0.75')
        dc = build_card({'mods': ['DC']}, {}, {})
        self.assertEqual(dc.to_layers()['mod_1_mult'], 'x0.75')

    def test_recent_lazer_accuracy_and_stable_comparison(self):
        score = {'accuracy': .880597, 'legacy_score_id': None,
                 'statistics': {'perfect':829, 'great':594, 'good':245,
                                'ok':66, 'meh':22, 'miss':60}}
        data = build_card(score, {}, {})
        self.assertEqual(data.accuracy, '88.05%')
        self.assertEqual(data.accuracy_lazer, '88.76%')
        self.assertEqual(data.to_layers()['_deco_accuracy_lazer_label'], 'STABLE ACC')
        score['legacy_score_id'] = 123
        stable = build_card(score, {}, {})
        self.assertEqual(stable.accuracy, '88.76%')
        self.assertEqual(stable.accuracy_lazer, '88.05%')
        self.assertEqual(stable.to_layers()['_deco_accuracy_lazer_label'], 'LAZER ACC')

    def test_new_map_fields_compact_score_and_full_combo(self):
        score = {'total_score': 995979, 'max_combo': 1234,
                 'is_perfect_combo': True, 'rank': 'S'}
        beatmap = {'bpm': 180, 'total_length': 165, 'cs': 4,
                   'status': 'ranked', 'max_combo': 1234}
        card = build_card(score, beatmap, {})
        self.assertEqual((card.length,card.keys),('2:45','4K'))
        self.assertEqual(card.status_icon,'ranked')
        self.assertEqual((card.score,card.score_suffix),('995K','.979'))
        self.assertTrue(card.full_combo)
        self.assertEqual(build_card({'total_score':979}, {}, {}).score, '979')
        self.assertEqual(build_card(score, {'status':'pending'}, {}).status_icon,'pending')
        self.assertEqual(build_card(score, {'status':'graveyard'}, {}).status_icon,'graveyard')

    def test_failed_status_wins_over_grade_and_accuracy(self):
        for rank in (None, '', 'S', 'X', 'C'):
            with self.subTest(rank=rank):
                self.assertEqual(self.grade(rank=rank, passed=False, accuracy=1), 'F')
        self.assertEqual(self.grade(rank=' f ', accuracy=1), 'F')
        self.assertEqual(self.grade(rank='F', passed=True, accuracy=1), 'F')

    def test_authoritative_grades_remain_unchanged(self):
        for raw, expected in [('X','SS'), ('XH','XH'), ('SS','SS'), ('SH','SH'),
                              ('S','S'), ('A','A'), ('B','B'), ('C','C'), ('D','D')]:
            with self.subTest(rank=raw):
                self.assertEqual(self.grade(rank=raw, passed=True, accuracy=0.1), expected)

    def test_accuracy_thresholds_including_boundaries(self):
        for acc, expected in [(0,'D'), (.699999,'D'), (.7,'C'), (.799999,'C'),
                              (.8,'B'), (.899999,'B'), (.9,'A'), (.949999,'A'),
                              (.95,'S'), (.999999,'S'), (1,'SS')]:
            with self.subTest(accuracy=acc):
                self.assertEqual(self.grade(passed=True, accuracy=acc), expected)

    def test_judgements_fallback_uses_weighted_accuracy(self):
        for stats, expected in [(dict(great=10), 'SS'), (dict(great=95,miss=5),'S'),
                                (dict(great=9,miss=1),'A'), (dict(great=8,miss=2),'B'),
                                (dict(great=7,miss=3),'C'), (dict(meh=10),'D'),
                                (dict(good=10),'D'), ({},'D')]:
            with self.subTest(stats=stats):
                self.assertEqual(self.grade(statistics=stats), expected)

    def test_lazer_accuracy_is_not_replaced_by_stable_accuracy(self):
        self.assertEqual(self.grade(accuracy=.69, statistics=dict(great=10)), 'D')

    def test_silver_grades_and_invalid_rank_fallback(self):
        for mod in ('HD','FL','FI'):
            with self.subTest(mod=mod):
                self.assertEqual(self.grade(accuracy=1, mods=[mod]), 'XH')
                self.assertEqual(self.grade(accuracy=.96, mods=[mod]), 'SH')
                self.assertEqual(self.grade(accuracy=.5, mods=[mod]), 'D')
        self.assertEqual(self.grade(rank='unknown', accuracy=.81), 'B')


if __name__ == '__main__':
    unittest.main()
