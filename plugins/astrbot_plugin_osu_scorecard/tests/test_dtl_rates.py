import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
import test_detail_packages as package_base
import main
from beatmap_details import detail_args


class DetailRatesTest(package_base.DetailPackagesTest):
    async def test_bare_speed_syntax_routes_for_both_commands(self):
        for command in ('dtl','dtlp'):
            for argument,rate in [('dt',1.5),('ht',.75),('1.2',1.2),('0.5',.5)]:
                with self.subTest(command=command,argument=argument),patch.object(main,'BeatmapDetails') as factory:
                    self.event.message_str=f'.{command} 4312004 {argument}'
                    factory.return_value.compact=AsyncMock(return_value=Path('compact.png'))
                    factory.return_value.pages=AsyncMock(return_value=[])
                    handler=self.plugin.detail_card if command=='dtl' else self.plugin.detail_pro
                    [x async for x in handler(self.event)]
                    method=factory.return_value.compact if command=='dtl' else factory.return_value.pages
                    method.assert_awaited_once_with(4312004,speed_rate=rate)

    async def test_dtl_single_file_dt_calls_compact_with_local_source(self):
        self.event.message_str='.dtl -dt'
        self.reader._collect_osz.return_value=(self.maps[:1],[])
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.compact=AsyncMock(return_value=Path('compact.png'))
            result=[x async for x in self.plugin.detail_card(self.event)]
            self.reader._collect_osz.assert_awaited_once_with(self.event,details_only=True)
            factory.return_value.compact.assert_awaited_once_with(self.maps[0]['beatmap_id'],speed_rate=1.5)
            self.assertEqual(result,['compact.png'])

    async def test_dtlp_custom_rate_is_kept_in_selection(self):
        self.event.message_str='.dtlp -rate 1.2'
        listing=[x async for x in self.plugin.detail_pro(self.event)]
        self.assertIn('1.2×',listing[0])
        self.event.get_messages.return_value=[main.Comp.Reply(id='123'),main.Comp.Plain('2')]
        self.event.bot.api.call_action.return_value={'raw_message':listing[0],'sender':{'user_id':'10001'}}
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.pages=AsyncMock(return_value=[])
            [x async for x in self.plugin.detail_package_choice(self.event)]
            factory.return_value.pages.assert_awaited_once_with(self.maps[1]['beatmap_id'],speed_rate=1.2)

    async def test_dtl_list_selection_can_override_rate(self):
        self.event.message_str='.dtl -ht'
        listing=[x async for x in self.plugin.detail_card(self.event)]
        self.assertIn('（dtl）',listing[0])
        self.event.get_messages.return_value=[main.Comp.Reply(id='123'),main.Comp.Plain('2 -dt')]
        self.event.bot.api.call_action.return_value={'raw_message':listing[0],'sender':{'user_id':'10001'}}
        with patch.object(main,'BeatmapDetails') as factory:
            factory.return_value.compact=AsyncMock(return_value=Path('compact.png'))
            [x async for x in self.plugin.detail_package_choice(self.event)]
            factory.return_value.compact.assert_awaited_once_with(self.maps[1]['beatmap_id'],speed_rate=1.5)


class DetailArgumentsTest(unittest.TestCase):
    def test_supported_arguments(self):
        for raw,expected in [('4312004 -dt',('4312004',1.5)),('-ht',('',.75)),
                             ('4312004 -rate 1.2',('4312004',1.2)),('-rate=1.1',('',1.1)),
                             ('4312004 dt',('4312004',1.5)),('4312004 ht',('4312004',.75)),
                             ('4312004 1.2',('4312004',1.2)),('4312004 0.5',('4312004',.5)),
                             ('0.5',('',.5)),('2 1.2',('2',1.2)),('4312004 2',('4312004',2.0))]:
            with self.subTest(raw=raw):self.assertEqual(detail_args(raw),expected)

    def test_ambiguous_and_invalid_rate_rejected(self):
        for raw in ('-dt -ht','-dt -rate 1.2','-rate nan','-rate inf','-rate 0','-rate 3.1','-rate','4312004 invalid','4312004 dt 1.2','4312004 0.5 ht'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):detail_args(raw)
