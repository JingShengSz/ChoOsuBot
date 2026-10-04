import asyncio
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from play_history import PlayHistory, recent_plays
from store import Store
from main import OsuScoreCardPlugin
from raster import render_mod_row


def play(stamp, sid=1, bid=42):
    return dict(id=sid, ended_at=datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                beatmap={'id':bid},beatmapset={'covers':{'cover':'https://example.org/cover.jpg'}},
                statistics={'perfect':10},mods=[{'acronym':'NC'}],pp=123,max_combo=10)


class HistoryTests(unittest.TestCase):
    def test_24h_boundary_and_invalid_dates(self):
        rows=[play(100000-86401,1),play(100000-86400,2),play(100000,3),play(100001,4),{}]
        self.assertEqual([s['id'] for s in recent_plays(rows,100000)],[3,2])

    def test_persistence_dedup_latest_and_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'history.sqlite3'; h=PlayHistory(path)
            for sid,stamp in [(1,100000),(2,100001),(1,100000)]:
                h.record('qq','User','mania','osu',dict(play(stamp,sid),access_token='SECRET'))
            h.record('other','User','mania','osu',play(100010,3))
            h.record('qq','User','mania','sb',play(100020,4))
            h.record('qq','User','osu','osu',play(100030,5))
            h=PlayHistory(path)
            result=h.latest('qq','user','mania','osu',42)
            self.assertEqual(result['id'],2)
            self.assertEqual(result['mods'],[{'acronym':'NC'}])
            self.assertEqual(result['pp'],123)
            self.assertNotIn('access_token',result)
            self.assertIsNone(h.latest('qq','new-binding','mania','osu',42))
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM plays').fetchone()[0],5)

    def test_missing_badge_preserves_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            sheet,placed=render_mod_row(['NC','DT'],Path(tmp))
            self.assertEqual([r['code'] for r in placed],['NC','DT'])
            self.assertIsNotNone(sheet.getbbox())


class Event:
    def __init__(self,text='r'): self.message_str=text
    def get_sender_id(self): return 'qq'
    def plain_result(self,text): return text


class CommandTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p=object.__new__(OsuScoreCardPlugin)
        self.p.config={'ruleset':'mania'}
        self.p.store=Store(Path(self.tmp.name))
        self.p.history=PlayHistory(Path(self.tmp.name)/'plays.sqlite3')
        self.p._user_token=AsyncMock(return_value='test-token')
        self.p._render_score=AsyncMock(return_value=Path('card.png'))
        self.p._image_reply=lambda event,png: 'IMAGE'

    async def collect(self, gen): return [r async for r in gen]

    async def test_unbound_never_queries_api(self):
        self.p._client=Mock(side_effect=AssertionError('must not query'))
        reply=await self.collect(self.p._map_card(Event(),42))
        self.assertIn('请先绑定',reply[0])

    async def test_command_spellings(self):
        async def lookup(event,bid,server): yield (bid,server)
        self.p._map_card=lookup
        for text,method in [('s 42',self.p.specific),('s42',self.p.specific_compact),
                            ('.s42 -sb',self.p.specific_compact),('.s 42 -sb',self.p.specific)]:
            with self.subTest(text=text):
                self.assertEqual(await self.collect(method(Event(text))),[(42,'sb' if '-sb' in text else 'osu')])

    async def test_recent_records_before_render_and_empty_message(self):
        import time
        self.p.store.bind('qq','User','mania','osu')
        score=play(time.time())
        self.p._recent_scores=AsyncMock(return_value=('ok',score,''))
        self.assertEqual(await self.collect(self.p.played(Event())),['IMAGE'])
        self.assertEqual(self.p.history.latest('qq','User','mania','osu',42)['id'],1)
        self.p._recent_scores=AsyncMock(return_value=('empty',None,''))
        self.assertEqual(await self.collect(self.p.played(Event())),['24h没有游玩记录。'])

    async def test_api_failure_uses_own_archive(self):
        self.p.store.bind('qq','User','mania','osu')
        self.p.history.record('qq','User','mania','osu',play(100000))
        self.p._client=Mock(side_effect=RuntimeError('HTTP 404'))
        reply=await self.collect(self.p._map_card(Event(),42))
        self.assertEqual(reply,['使用记录库中该谱面的最近一次成绩。','IMAGE'])

    async def test_newest_of_api_and_archive(self):
        self.p.store.bind('qq','User','mania','osu')
        self.p.history.record('qq','User','mania','osu',play(100000,1))
        client=Mock()
        client.user_by_name.return_value={'id':7,'username':'User'}
        client.beatmap_user_scores.return_value=[play(99999,2),play(100001,3)]
        client.get.return_value={'id':42,'beatmapset':{}}
        self.p._client=lambda:client
        self.assertEqual(await self.collect(self.p._map_card(Event(),42)),['IMAGE'])
        self.assertEqual(self.p._render_score.call_args.args[1]['id'],3)

    async def test_both_recent_backends_enforce_24h(self):
        client=Mock();client.recent_scores.return_value=[play(100000)]
        self.p._client=lambda:client
        self.assertEqual((await self.p._recent_scores('User',True,'mania',user_token='test'))[0],'empty')
        client.player_scores.return_value=[dict(play(100000),play_time='1970-01-02T00:00:00')]
        self.p._sb=lambda:client;self.p._sb_player_id=AsyncMock(return_value=7)
        self.assertEqual((await self.p._sb_recent('User',False,'mania'))[0],'empty')


if __name__=='__main__': unittest.main()
