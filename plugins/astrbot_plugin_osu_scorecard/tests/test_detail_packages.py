import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import test_detail_commands as detail_base
import main

class DetailPackagesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await detail_base.DetailCommandsTest.asyncSetUp(self)
        self.reader=Mock(server='http://127.0.0.1:8760')
        self.maps=[{'beatmap_id':f'local-{"a"*32}-{i}', 'title':'Pack', 'version':f'Diff {i}', 'keys':4} for i in range(2)]
        self.reader._collect_osz=AsyncMock(return_value=(self.maps,[]))
        self.plugin.context=Mock()
        self.plugin.context.get_registered_star.return_value=SimpleNamespace(activated=True,star_cls=self.reader)
        self.event.get_messages.return_value=[]
        self.event.bot=Mock()
        self.event.bot.api.call_action=AsyncMock()

    async def test_single_osz_analyses_local_file_without_official_id(self):
        self.reader._collect_osz.return_value=(self.maps[:1],[])
        self.plugin.history.remember_chat_map('group-a',5812833)
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.pages=AsyncMock(return_value=[Path(f'detail_{i}.png') for i in range(3)])
            result=[x async for x in self.plugin.detail_pro(self.event)]
            self.reader._collect_osz.assert_awaited_once_with(self.event,details_only=True)
            factory.return_value.pages.assert_awaited_once_with(self.maps[0]['beatmap_id'])
            self.assertEqual(len(result),1)
            self.assertIn('本地谱面',result[0].chain[0].nodes[0].content[0].text)

    async def list_package(self):
        result=[x async for x in self.plugin.detail_pro(self.event)]
        self.assertIn('请选择要分析的难度（dtlp）',result[0])
        self.event.get_messages.return_value=[main.Comp.Reply(id='123'),main.Comp.At(qq='10001'),main.Comp.Plain('2')]
        self.event.bot.api.call_action.return_value={'raw_message':result[0], 'sender':{'user_id':'10001'}}
        return result[0]

    async def test_reply_number_with_bot_mention_selects_second_chart_once(self):
        await self.list_package()
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.pages=AsyncMock(return_value=[Path(f'detail_{i}.png') for i in range(3)])
            stream=self.plugin.detail_package_choice(self.event)
            result=[await anext(stream)]
            self.event.stop_event.assert_not_called()
            with self.assertRaises(StopAsyncIteration):
                await anext(stream)
            factory.return_value.pages.assert_awaited_once_with(self.maps[1]['beatmap_id'])
            self.assertEqual(len(result),1)
            self.event.stop_event.assert_called_once()
            again=[x async for x in self.plugin.detail_package_choice(self.event)]
            self.assertIn('已过期',again[0])
            factory.return_value.pages.assert_awaited_once()

    async def test_another_user_expired_and_old_list_cannot_select(self):
        await self.list_package()
        with patch.object(main,'BeatmapDetails') as factory:
            self.event.get_sender_id.return_value='other-user'
            self.assertIn('没有对应',[x async for x in self.plugin.detail_package_choice(self.event)][0])
            self.event.get_sender_id.return_value='another-person'
            pending=self.plugin._detail_choices[('group-a','another-person')]
            original_time=pending['time'];pending['time']-=1801
            self.assertIn('已过期',[x async for x in self.plugin.detail_package_choice(self.event)][0])
            pending['time']=original_time;pending['token']='new-list-token'
            self.assertIn('没有对应',[x async for x in self.plugin.detail_package_choice(self.event)][0])
            factory.assert_not_called()

    async def test_om_list_and_mentions_of_others_are_ignored(self):
        await self.list_package()
        self.event.bot.api.call_action.return_value={'raw_message':'请选择要渲染的难度：回复本列表发送编号'}
        self.assertEqual([x async for x in self.plugin.detail_package_choice(self.event)],[])
        self.event.stop_event.assert_not_called()
        self.event.get_messages.return_value=[main.Comp.Reply(id='123'),main.Comp.At(qq='someone-else'),main.Comp.Plain('2')]
        self.assertEqual([x async for x in self.plugin.detail_package_choice(self.event)],[])

    async def test_dtlp_two_is_official_id_and_does_not_import_package(self):
        self.event.message_str='.dtlp 2'
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.pages=AsyncMock(return_value=[])
            [x async for x in self.plugin.detail_pro(self.event)]
            factory.return_value.pages.assert_awaited_once_with(2)
            self.reader._collect_osz.assert_not_awaited()

if __name__=='__main__':unittest.main()
