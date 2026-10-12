import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main
from play_history import PlayHistory

class DetailCommandsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.plugin=object.__new__(main.OsuScoreCardPlugin)
        self.plugin.config={}; self.plugin.data_dir=Path(self.tmp.name)
        self.plugin.history=PlayHistory(self.plugin.data_dir/'plays.sqlite3')
        self.event=Mock(message_str='.dtlp',unified_msg_origin='group-a')
        self.event.get_sender_id.return_value='another-person'
        self.event.get_platform_name.return_value='aiocqhttp'
        self.event.get_self_id.return_value='10001'
        self.event.plain_result.side_effect=lambda text:text
        self.event.image_result.side_effect=lambda path:path
        self.event.chain_result.side_effect=lambda chain: main.MessageChain(chain)

    async def test_dtl_sends_one_card_for_explicit_map(self):
        self.event.message_str='.dtl 4312004'
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.compact=AsyncMock(return_value=Path('compact.png'))
            result=[x async for x in self.plugin.detail_card(self.event)]
            factory.return_value.compact.assert_awaited_once_with(4312004)
            self.assertEqual(result,['compact.png'])
            factory.return_value.pages.assert_not_called()

    async def test_dtl_blank_uses_latest_chat_map(self):
        self.event.message_str='.dtl'
        self.plugin.history.remember_chat_map('group-a',4312004)
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.compact=AsyncMock(return_value=Path('compact.png'))
            result=[x async for x in self.plugin.detail_card(self.event)]
            factory.return_value.compact.assert_awaited_once_with(4312004)
            self.assertEqual(result,['compact.png'])

    async def test_blank_uses_chat_map_without_binding_and_sends_three_pages(self):
        self.plugin.history.remember_chat_map('group-a',5812833)
        self.plugin.history.remember_chat_map('group-b',123)
        pages=[Path(f'detail_{i}.png') for i in range(1,4)]
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.pages=AsyncMock(return_value=pages)
            result=[x async for x in self.plugin.detail_pro(self.event)]
            factory.return_value.pages.assert_awaited_once_with(5812833)
            self.assertEqual(len(result),1)
            self.assertEqual(len(result[0].chain),1)
            forward=result[0].chain[0]
            self.assertIsInstance(forward,main.Comp.Nodes)
            self.assertEqual(len(forward.nodes),3)
            self.assertEqual([n.content[1].file for n in forward.nodes],
                             [main.Comp.Image.fromFileSystem(str(p)).file for p in pages])
            self.event.plain_result.assert_not_called()
            self.event.image_result.assert_not_called()

    async def test_qq_adapter_sends_one_forward_with_three_images_in_group_and_private(self):
        from PIL import Image
        from aiocqhttp import Event
        from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
        pages=[]
        bodies=[]
        for i in range(1,4):
            page=Path(self.tmp.name)/f'detail_{i}.png'
            Image.new('RGB',(2,2),(i*70,0,0)).save(page)
            pages.append(page);bodies.append(page.read_bytes())
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.pages=AsyncMock(return_value=pages)
            results=[x async for x in self.plugin._detail_reply(self.event,'5812833')]
        self.assertEqual(len(results),1)
        import base64
        for is_group in (True,False):
            with self.subTest(is_group=is_group):
                bot=Mock();bot.call_action=AsyncMock()
                await AiocqhttpMessageEvent.send_message(bot,results[0],Event({'self_id':10001}),is_group,'20002')
                bot.call_action.assert_awaited_once()
                args,kwargs=bot.call_action.await_args
                self.assertEqual(args[0],'send_group_forward_msg' if is_group else 'send_private_forward_msg')
                self.assertEqual(kwargs['group_id' if is_group else 'user_id'],'20002')
                messages=kwargs['messages'];self.assertEqual(len(messages),3)
                for i,node in enumerate(messages):
                    self.assertEqual(node['data']['user_id'],'10001')
                    content=node['data']['content']
                    self.assertIn(f'{i+1}/3',content[0]['data']['text'])
                    self.assertEqual(content[1]['type'],'image')
                    encoded=content[1]['data']['file'].removeprefix('base64://')
                    self.assertEqual(base64.b64decode(encoded),bodies[i])

    async def test_explicit_id_overrides_recent_map_and_compact_form(self):
        self.plugin.history.remember_chat_map('group-a',123)
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.pages=AsyncMock(return_value=[])
            for text,handler in [('.dtlp 5812833',self.plugin.detail_pro),('.dtlp5812833',self.plugin.detail_pro_compact)]:
                self.event.message_str=text
                [x async for x in handler(self.event)]
                factory.return_value.pages.assert_awaited_with(5812833)

    async def test_missing_map_and_invalid_argument_do_not_call_service(self):
        with patch.object(main,'BeatmapDetails') as factory:
            result=[x async for x in self.plugin.detail_pro(self.event)]
            self.assertIn('本聊天',result[0])
            for raw in ('0','-1','abc','12 34','5812833 -sb'):
                result=[x async for x in self.plugin._detail_reply(self.event,raw)]
                self.assertIn('用法',result[0])
            factory.assert_not_called()

    async def test_service_failure_reports_error_without_images(self):
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.pages=AsyncMock(side_effect=RuntimeError('只支持 osu!mania'))
            result=[x async for x in self.plugin._detail_reply(self.event,'5812833')]
            self.assertIn('只支持 osu!mania',result[-1])
            self.event.image_result.assert_not_called()

if __name__=='__main__': unittest.main()
