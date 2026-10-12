"""Malody Key charts and 4.x MR input, based on Mania-Replay-Master.

Reference: https://github.com/Mania-Visualization-Project/Mania-Replay-Master
The MR layout follows replay/MalodyReplayReader.kt (Apache-2.0).
MC charts are converted into the existing renderer's osu text contract.
"""

from __future__ import annotations

import bisect
import json
import math
import struct


def beat_value(value):
    if not isinstance(value, list) or len(value) != 3 or not value[2]:
        raise ValueError("Malody beat 必须是 [整数, 分子, 分母]")
    result = float(value[0]) + float(value[1]) / float(value[2])
    if not math.isfinite(result):
        raise ValueError("Malody beat 非有限数值")
    return result


def convert_chart(raw: bytes) -> tuple[str, dict]:
    """Convert Key MC timing, offset, taps, holds and scroll effects to osu text."""
    data = json.loads(raw.decode("utf-8-sig"))
    meta = data["meta"]
    if meta.get("mode") not in (0, 6):
        raise ValueError("Malody 仅支持 Key 模式（mode 0/6）")
    keys = int(meta["mode_ext"]["column"])
    if not 1 <= keys <= 10:
        raise ValueError("暂不支持：Malody 键数必须在 1–10K")
    stamps = sorted(data["time"], key=lambda row: beat_value(row["beat"]))
    if not stamps:
        raise ValueError("Malody 缺少 BPM 时间点")
    beats = [beat_value(row["beat"]) for row in stamps]
    bpms = [float(row["bpm"]) for row in stamps]
    if any(not math.isfinite(bpm) or bpm <= 0 for bpm in bpms):
        raise ValueError("Malody BPM 必须为正数")
    sounds = [
        row for row in data["note"] if row.get("sound") and row.get("type", 1) == 1
    ]
    if not sounds:
        raise ValueError("Malody 缺少背景音乐事件")
    sound = sounds[-1]
    audio = str(sound["sound"])
    # Chart beat zero and replay timestamps share one timeline. Sound starts at
    # beat(sound) + offset; subtract that position so audio starts at output zero.
    times = [0.0]
    for i in range(1, len(stamps)):
        times.append(times[-1] + (beats[i] - beats[i - 1]) * 60000 / bpms[i - 1])

    def millis(beat):
        value = beat_value(beat)
        i = max(0, bisect.bisect_right(beats, value) - 1)
        return times[i] + (value - beats[i]) * 60000 / bpms[i]

    audio_start = millis(sound.get("beat", [0, 0, 1])) + float(sound.get("offset", 0))
    song = meta.get("song") or {}

    def clean(value):
        return str(value).replace("\r", " ").replace("\n", " ")

    bg = clean(meta.get("background", ""))
    lines = [
        "osu file format v14",
        "[General]",
        f"AudioFilename: {clean(audio)}",
        "Mode: 3",
        "[Metadata]",
        f"Title:{clean(song.get('title', 'Malody'))}",
        f"Artist:{clean(song.get('artist', ''))}",
        f"Creator:{clean(meta.get('creator', ''))}",
        f"Version:{clean(meta.get('version', 'Malody'))}",
        "Source:Malody",
        "[Difficulty]",
        f"CircleSize:{keys}",
        "OverallDifficulty:5",
        "HPDrainRate:5",
        "[Events]",
    ]
    if bg:
        lines.append("0,0," + json.dumps(bg, ensure_ascii=False) + ",0,0")
    lines.append("[TimingPoints]")
    for i, row in enumerate(stamps):
        lines.append(
            f"{round(times[i] - audio_start)},{60000 / bpms[i]:.8f},{int(row.get('sign', 4))},1,0,100,1,0"
        )
    for row in data.get("effect", []):
        if "scroll" not in row:
            continue
        scroll = float(row["scroll"])
        if not math.isfinite(scroll) or scroll < 0:
            raise ValueError("暂不支持负数 Malody Scroll")
        lines.append(
            f"{round(millis(row['beat']) - audio_start)},{-100 / scroll if scroll else -1e308},4,1,0,100,0,0"
        )
    lines.append("[HitObjects]")
    notes = sorted(
        (row for row in data["note"] if "column" in row),
        key=lambda row: beat_value(row["beat"]),
    )
    if not notes:
        raise ValueError("Malody 没有 Key 音符")
    for row in notes:
        column = int(row["column"])
        if not 0 <= column < keys:
            raise ValueError("Malody 音符轨道超出键数")
        start = round(millis(row["beat"]) - audio_start)
        x = int((512 * column + 256) / keys)
        if "endbeat" in row:
            end = round(millis(row["endbeat"]) - audio_start)
            if end < start:
                raise ValueError("Malody 长条结束早于开始")
            lines.append(f"{x},192,{start},128,0,{end}:0:0:0:0:")
        else:
            lines.append(f"{x},192,{start},1,0,0:0:0:0:")
    return "\n".join(lines) + "\n", {
        "source": "malody",
        "replay_shift_ms": -audio_start,
    }


MR_WINDOWS = (
    (52, 92, 126, 150),
    (44, 84, 118, 150),
    (36, 76, 110, 150),
    (28, 68, 102, 150),
    (20, 60, 94, 150),
)


def parse_mr(raw: bytes) -> dict:
    """Decode the bounded little-endian Malody 4.x MR header and key events."""
    if len(raw) > 32 * 1024**2:
        raise ValueError("回放超过32MB")
    position = 0

    def read(fmt):
        nonlocal position
        size = struct.calcsize(fmt)
        if position + size > len(raw):
            raise ValueError("Malody 回放数据被截断")
        values = struct.unpack_from(fmt, raw, position)
        position += size
        return values[0] if len(values) == 1 else values

    def string():
        nonlocal position
        size = read("<i")
        if not 0 <= size <= 65536 or position + size > len(raw):
            raise ValueError("Malody 回放字符串不合法")
        value = raw[position : position + size].decode("utf-8", "replace")
        position += size
        return value

    if string() != "mr format head":
        raise ValueError("不是已支持的 Malody 4.x MR 格式；Malody V 回放需要样本核验")
    version = read("<I")
    if version >> 16 != 4:
        raise ValueError("此 MR 版本尚未验证；Malody V 回放需要样本核验")
    md5, difficulty, title, username = (string() for _ in range(4))
    score, combo, best, cool, good, miss, miss2, mods, judge = read("<9i")
    if not 0 <= judge < 5 or any(n < 0 for n in (best, cool, good, miss, miss2)):
        raise ValueError("Malody 回放判定数据不合法")
    if string() != "mr data":
        raise ValueError("Malody 回放缺少 mr data")
    data_version = read("<I")
    if data_version != version:
        raise ValueError("Malody MR 数据版本与头部不一致")
    count = read("<i")
    read("<B")
    read("<i")
    read("<I")
    if not 0 <= count <= 1000000 or count * 6 > len(raw) - position:
        raise ValueError("Malody 回放按键数量不合法")
    presses, releases = [], []
    for _ in range(count):
        timestamp, action, column = read("<iBB")
        if action not in (1, 2) or column >= 10:
            raise ValueError("Malody 回放包含不支持的按键事件")
        if timestamp >= 0:
            (presses if action == 1 else releases).append(
                {"time": timestamp, "key": column}
            )
    for events in (presses, releases):
        events.sort(key=lambda row: row["time"])
    rate = (
        1.2
        if mods & (1 << 4)
        else 1.5
        if mods & (1 << 5)
        else 0.8
        if mods & (1 << 8)
        else 1.0
    )
    return {
        "source": "malody",
        "version": version,
        "data_version": data_version,
        "md5": md5.lower(),
        "difficulty": difficulty,
        "title": title,
        "username": username,
        "score": score,
        "max_combo": combo,
        "presses": presses,
        "releases": releases,
        "press_count": len(presses),
        "mirror": bool(mods & 4),
        "mods": mods,
        "rate": rate,
        "judge": judge,
        "windows": list(MR_WINDOWS[judge]),
        "counts": {
            "perfect": best,
            "great": cool,
            "good": good,
            "ok": 0,
            "meh": 0,
            "miss": miss,
        },
        "classic": False,
    }
