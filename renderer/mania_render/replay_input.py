"""Shared validated replay upload contract for jobs and the browser."""

from pathlib import Path
import json

from . import osz
from .malody import parse_mr
from .malody_v import parse_mrv
from .osr import parse_osr
from .fetch import lookup_bid_by_md5


def resolve_replay(
    path: Path, cache: Path, fallback_bid: str = "", platform: str = "pc"
) -> dict:
    if path.stat().st_size > 32 * 1024**2:
        raise ValueError("回放超过32MB")
    if path.suffix.lower() in (".mr", ".mrv"):
        data = (parse_mrv if path.suffix.lower() == '.mrv' else parse_mr)(path.read_bytes())
        settings = path.with_suffix(".json")
        if settings.is_file():
            platform = json.loads(settings.read_text(encoding="utf-8")).get(
                "platform", platform
            )
        if platform not in ("pc", "pe"):
            raise ValueError("Malody platform 必须是 pc 或 pe")
        if platform == "pe":
            data["windows"] = [window + 9 for window in data["windows"]]
        data["platform"] = platform
        bid = osz.find_by_md5(data["md5"])
        if fallback_bid and osz.is_local(fallback_bid):
            meta = osz.manifest(fallback_bid)["meta"]
            converted = data.get('format') == 'mrv' and osz.matches_converted_mrv(fallback_bid, data)
            if meta.get("chart_md5") != data["md5"] and not converted:
                raise ValueError("回放与选择的谱面 MD5 不匹配，请提供对应谱面包")
            bid = fallback_bid
            data['match_method'] = 'converted_osu_timeline' if converted else 'md5'
        if not bid and data.get('format') == 'mrv':
            bid = osz.find_converted_mrv(data)
            if bid:
                data['match_method'] = 'converted_osu_timeline'
        if not bid:
            raise ValueError(
                "未找到 Malody 回放对应谱面。请先回复包含音频的 .osz/.mcz/.zip 谱面包发送 v 导入，再回复 .mr/.mrv 发送 v"
            )
        meta = osz.manifest(bid)["meta"]
        shift = meta.get("replay_shift_ms", 0)
        for events in (data["presses"], data["releases"], data.get('recorded_judgements', [])):
            for event in events:
                if not 0 <= event["key"] < meta["keys"]:
                    raise ValueError("Malody 回放键数与谱面不匹配")
                event["time"] += shift
        if data.get('format') == 'mrv':
            from .osu_file import parse_osu
            chart = parse_osu(osz.text(bid))
            for column in range(chart.keys):
                notes = sorted((n for n in chart.hit_objects if n.column == column), key=lambda n:n.start_time)
                rows = [j for j in data['recorded_judgements'] if j['key'] == column]
                if len(notes) != len(rows):
                    raise ValueError('MRV 判定数量与该轨道谱面音符不一致')
                for note, row in zip(notes, rows):
                    if abs(note.start_time-row['time']) > 150:
                        raise ValueError('MRV 判定时间与谱面音符不一致')
                    row['obj_time'] = note.start_time
        data.update(bid=bid, found=True)
        return data
    head, replay = parse_osr(path)
    if head.ruleset_id != 3:
        raise ValueError("v 仅支持 osu!mania 回放")
    bid = osz.find_by_md5(head.beatmap_md5) or lookup_bid_by_md5(
        head.beatmap_md5 or "", cache
    )
    if osz.is_local(fallback_bid):
        if osz.manifest(fallback_bid)["meta"].get("chart_md5") != head.beatmap_md5:
            raise ValueError("回放与选择的谱面 MD5 不匹配")
        bid = fallback_bid
    return {
        "bid": bid or fallback_bid or "",
        "md5": head.beatmap_md5,
        "username": head.username,
        "score": head.score,
        "max_combo": head.max_combo,
        "ended_at": head.ended_at,
        "presses": [{"time": p.time_ms, "key": p.column} for p in replay.presses],
        "releases": [{"time": p.time_ms, "key": p.column} for p in replay.releases],
        "press_count": len(replay.presses),
        "mirror": head.mirror,
        "mods": head.mods,
        "mods_detail": head.mods_detail,
        "rate": head.clock_rate,
        "holds_to_notes": any(m.get("acronym") == "HO" for m in head.mods_detail),
        "client": "Stable" if head.version < 30000000 else "Lazer",
        "counts": head.counts,
        "classic": replay.classic,
        "found": bool(bid),
    }
