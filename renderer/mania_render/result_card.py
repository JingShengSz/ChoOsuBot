"""Replay result adapter using the same template and drawing modules as AstrBot p."""
from __future__ import annotations

import base64
import importlib
import io
import os
from pathlib import Path
import sys
import tempfile
import types


def render_result(payload: dict, root: Path) -> bytes:
    from PIL import Image
    # Repository checkout keeps shared files beside renderer/. Standalone nodes
    # can bundle the same pure drawing modules and template inside their root.
    package_default = root.parent / 'plugins' / 'astrbot_plugin_osu_scorecard'
    if not package_default.is_dir():
        package_default = root / 'plugins' / 'astrbot_plugin_osu_scorecard'
    template_default = root.parent / 'template' / 'layer_mapping.json'
    if not template_default.is_file():
        template_default = root / 'template' / 'layer_mapping.json'
    package = Path(os.environ.get('MANIA_SCORE_PLUGIN_DIR', package_default))
    template = Path(os.environ.get('MANIA_SCORE_TEMPLATE', template_default))
    if not package.is_dir() or not template.is_file():
        raise RuntimeError('成绩卡模板未安装，请配置 MANIA_SCORE_PLUGIN_DIR 和 MANIA_SCORE_TEMPLATE')
    name = '_mania_scorecard'
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__path__ = [str(package)]
        sys.modules[name] = module
    card, raster, heading, render = [importlib.import_module(f'{name}.{part}') for part in ('card','raster','heading','render')]
    bm = payload['beatmap']
    score = payload['score']
    counts = score.get('statistics') or {}
    if not isinstance(counts, dict) or any(not isinstance(n, int) or n < 0 or n > 1000000 for n in counts.values()):
        raise ValueError('判定数据无效')
    if score.get('source') == 'malody':
        score={**score,'accuracy':(counts.get('perfect',0)+.75*counts.get('great',0)+.4*counts.get('good',0))/max(1,sum(counts.values()))}
    data = card.build_card(score, bm, payload.get('beatmapset') or {}, pp_max_mode='dash',
        real_max_combo=payload.get('map_combo'), density_counts=payload.get('density') or [],fail_progress=payload.get('fail_progress'),bpm_range=payload.get('bpm_range'))
    if score.get('display_date'):
        data.play_date=score['display_date']
    if score.get('total_score') is None:
        data.score, data.score_suffix = '--', ''
    if score.get('source') == 'malody':
        data.server_tag = 'Malody'
        data.accuracy_lazer='--'
        data.other_accuracy_label=''
    if payload.get('autoplay'):
        data.player_name = 'Auto Play'
        data.server_tag = '自动播放'
    assets = template.parent / 'assets'
    work_root=root/'cache'/'result_work'
    work_root.mkdir(parents=True,exist_ok=True)
    engine = render.PilScoreCardRenderer(template, assets,work_root)
    wrapped = heading.render_wrapped_heading(data.title,data.artist)
    colors = {item['key']:item['color'] for item in engine.spec.get('rankColors', [])}
    jobs = []
    for key,value in data.to_layers().items():
        if key.startswith('mod_') and key.endswith('_mult'):
            continue
        if wrapped is not None and key in ('beatmap_title','beatmap_artist'):
            value = ''
        if key == 'server_tag' and raster.server_badge_path(assets/'ui_extra',data.server_tag).is_file():
            value = ''
        accent = colors.get(data.grade) if key == 'accuracy' else None
        if key == 'max_combo' and data.full_combo:
            accent = '#FFD35A'
        jobs.append({'name':key,'value':str(value or ''),'accent':accent})
    with tempfile.TemporaryDirectory(prefix='mania-result-',dir=work_root) as directory:
        work=Path(directory)
        rasters=[]
        def add(layer,image):
            target=work/f'{layer}.png'
            image.save(target)
            rasters.append({'layer':layer,'path':str(target)})
        def sheet():
            return Image.new('RGBA',(1920,1080))
        background=payload.get('background','')
        if background:
            if not background.startswith('data:image/jpeg;base64,'):
                raise ValueError('背景格式无效')
            image=Image.open(io.BytesIO(base64.b64decode(background.split(',',1)[1],validate=True)))
            if image.width > 4096 or image.height > 4096:
                raise ValueError('背景尺寸过大')
            add('beatmap_bg',raster.cover_fit(image))
        extras=raster.render_ui_extras(assets/'ui_extra',data.status_icon,data.server_tag)
        if wrapped is not None:
            extras.alpha_composite(wrapped)
        add('ui_extras',extras)
        add('score',raster.render_score_compact(data.score,data.score_suffix))
        image=sheet();image.alpha_composite(raster.render_star_strip(data.star_value,600),(60,310));add('star_strip',image)
        for layer,value,bounds,y in [('od_bar',data.od_value,data.od_range,520),('hp_bar',data.hp_value,data.hp_range,588)]:
            image=sheet();image.alpha_composite(raster.render_stat_bar(value,*bounds,width=600,height=12),(60,y));add(layer,image)
        image,placed=raster.render_mod_row(data.mods,assets/'mods'/'line_v1')
        image.alpha_composite(raster.render_mod_speed_labels(data.mod_speeds,placed))
        image.alpha_composite(raster.render_density_panel(data.density_counts,data.fail_progress,data.ratio_text,data.star_value))
        add('mod_1',image)
        for layer,file in [('_deco_bg_gradient',f'tint_{data.grade}.png'),('rank_glow',f'glow_{data.grade}.png')]:
            target=assets/'rank_svg'/file
            if target.is_file():
                rasters.append({'layer':layer,'path':str(target)})
        output=work/'result.png'
        engine.render(jobs,rasters,engine.signboard_chain(data.grade),output)
        return output.read_bytes()
