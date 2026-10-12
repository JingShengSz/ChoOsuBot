import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mames_api import MamesApi, normalize_score
from card import build_card
from store import Store
from main import OsuScoreCardPlugin


class MamesTests(unittest.TestCase):
    def test_suffix_and_binding_isolation(self):
        self.assertEqual(OsuScoreCardPlugin._split_server('Grok AI -mames'), ('Grok AI', 'mames'))
        self.assertEqual(OsuScoreCardPlugin._split_server('-sb'), ('', 'sb'))
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            for server in ('osu', 'sb', 'mames'):
                store.bind('qq', server + ' user', 'mania', server)
            self.assertEqual(store.username_for('qq', 'mames'), 'mames user')
            store.unbind('qq', 'mames')
            self.assertEqual(store.username_for('qq', 'osu'), 'osu user')
            self.assertEqual(store.username_for('qq', 'sb'), 'sb user')

    def test_client_identity_preserves_native_mod_speed(self):
        stable = normalize_score({'legacy_score_id': 12, 'build_id': None, 'passed': False})
        lazer = normalize_score({'legacy_score_id': None, 'build_id': 99, 'legacy_total_score': 123,
                                 'mods': [{'acronym': 'HT', 'settings': {'speed_change': .8}}]})
        self.assertEqual(build_card(stable, {}, {}).server_tag, 'Mames Stable')
        self.assertEqual(build_card(stable, {}, {}).grade, 'F')
        card = build_card(lazer, {}, {})
        self.assertEqual(card.server_tag, 'Mames Lazer')
        self.assertEqual(card.other_accuracy_label, 'STABLE ACC')
        self.assertEqual(card.to_layers()['mod_1_mult'], 'x0.8')

    def test_recent_keeps_fail_option_and_normalizes(self):
        api = MamesApi()
        api.get = Mock(return_value=[{'legacy_score_id': None, 'passed': False}])
        result = api.recent_scores(123, 'mania', include_fails=True)
        self.assertEqual(result[0]['server'], 'mames')
        self.assertEqual(api.get.call_args.args[1]['include_fails'], 1)

    def test_username_collapses_accidental_whitespace(self):
        api = MamesApi()
        def get(endpoint):
            if endpoint == '/users/Grok%20AI/mania':
                return {'id': 5410, 'username': 'Grok AI'}
            return {}
        api.get = Mock(side_effect=get)
        self.assertEqual(api.user_by_name('  Grok  AI  ', 'mania')['id'], 5410)
        self.assertEqual(api.get.call_args.args[0], '/users/Grok%20AI/mania')
