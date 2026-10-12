import time
from pathlib import Path
from unittest.mock import AsyncMock
import unittest
import test_history_commands as fixtures
from test_history_commands import Event, play
from main import Comp


class TargetEvent(Event):
    def __init__(self, text, mentions=()):
        super().__init__(text)
        self.mentions = mentions
    def get_messages(self): return [Comp.At(qq=q) for q in self.mentions]
    def get_self_id(self): return 'bot'


class TargetTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.CommandTests.asyncSetUp
    collect = fixtures.CommandTests.collect
    async def test_target_resolution_isolated_by_server(self):
        self.p.store.bind('123','SB User','taiko','sb')
        self.p.store.bind('123','Mames User','mania','mames')
        self.assertEqual(self.p._query_target(TargetEvent('p', ['123']), '@123', 'sb'),
                         ('123','SB User','taiko'))
        self.assertEqual(self.p._query_target(Event('p @123'), '@123', 'mames'),
                         ('123','Mames User','mania'))
        with self.assertRaisesRegex(ValueError, '尚未绑定'):
            self.p._query_target(Event(), '@123','osu')
        self.assertEqual(self.p._query_target(Event(), 'Grok  AI', 'mames'),
                         ('','Grok AI','mania'))

    async def test_recent_name_does_not_record_caller_ownership(self):
        self.p._recent_scores=AsyncMock(return_value=('ok',play(time.time()),''))
        self.assertEqual(await self.collect(self.p.played(Event('r Other User -mames'))), ['IMAGE'])
        self.assertEqual(self.p._recent_scores.call_args.args[:4], ('Other User', True, 'mania', 'mames'))
        self.assertIsNone(self.p.history.latest('qq','Other User','mania','mames',42))
        self.assertIsNotNone(self.p.history.latest('','Other User','mania','mames',42))

    async def test_recent_mention_uses_target_token_mode_and_history(self):
        self.p.store.bind('123','Target','taiko','osu')
        self.p._recent_scores=AsyncMock(return_value=('ok',play(time.time()),''))
        self.assertEqual(await self.collect(self.p.played(TargetEvent('r @123',['123']))), ['IMAGE'])
        self.p._user_token.assert_not_awaited()
        self.assertEqual(self.p._recent_scores.call_args.args[:4], ('Target',True,'taiko','osu'))
        self.assertIsNotNone(self.p.history.latest('123','Target','taiko','osu',42))

    async def test_map_target_spellings(self):
        async def lookup(event,bid,server,target=''): yield (bid,server,target)
        self.p._map_card=lookup
        for text,method in [('s 42 Grok AI -mames',self.p.specific),
                            ('s42 @123 -sb',self.p.specific_compact)]:
            expected=(42,'mames','Grok AI') if '-mames' in text else (42,'sb','@123')
            self.assertEqual(await self.collect(method(Event(text))),[expected])

    async def test_missing_target_auth_does_not_authorize_caller(self):
        self.p.store.bind('123','Target','mania','osu')
        self.p._recent_scores=AsyncMock(return_value=('needs_user_token',None,''))
        self.p._send_oauth_link=AsyncMock(side_effect=AssertionError('must not send'))
        result=await self.collect(self.p.played(TargetEvent('r @123',['123'])))
        self.assertIn('暂时无法访问',result[0])

    async def test_named_map_uses_account_archive_without_caller_binding(self):
        self.p.history.record('123','Target','mania','mames',play(100000))
        self.p._any_client=lambda server: (_ for _ in ()).throw(RuntimeError('offline'))
        result=await self.collect(self.p._map_card(Event(),42,'mames','Target'))
        self.assertEqual(result,['使用记录库中该谱面的最近一次成绩。','IMAGE'])
        self.p._render_score.assert_awaited_once()
        self.assertEqual(self.p._render_score.call_args.kwargs['ruleset'],'mania')
        self.assertIsNone(self.p.history.latest_account('Target','mania','sb',42))

    async def test_public_recent_without_personal_authorization(self):
        from unittest.mock import Mock
        client=Mock()
        client.recent_scores.return_value=[play(time.time())]
        self.p._client=lambda:client
        status,score,_=await self.p._recent_scores('Other',True,'mania')
        self.assertEqual(status,'ok')
        self.assertIsNone(client.recent_scores.call_args.kwargs['user_token'])

    async def test_unknown_player_404_is_not_authorization(self):
        from unittest.mock import Mock
        client=Mock()
        client.recent_scores.side_effect=RuntimeError('osu! API HTTP 404 at /api/v2/users/unknown/mania')
        self.p._client=lambda:client
        with self.assertRaisesRegex(RuntimeError,'找不到这个 osu! 玩家'):
            await self.p._recent_scores('unknown',True,'mania')
