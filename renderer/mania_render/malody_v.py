"""Bounded reader for the protobuf MRV layout verified with a Malody V sample.

Unknown fields are skipped. Recorded judgements and combo snapshots are used
directly; the V judgement engine is not inferred from the 4.x implementation.
"""

import math
import re
import struct


def _fields(raw):
    position = 0

    def varint():
        nonlocal position
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(raw):
                raise ValueError("MRV 数据被截断")
            byte = raw[position]
            position += 1
            if shift == 63 and byte > 1:
                raise ValueError("MRV varint 超出范围")
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError("MRV varint 不合法")

    while position < len(raw):
        tag = varint()
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError("MRV 字段编号不合法")
        if wire == 0:
            value = varint()
        elif wire in (1, 2, 5):
            size = varint() if wire == 2 else 8 if wire == 1 else 4
            if size > len(raw) - position:
                raise ValueError("MRV 数据被截断")
            value = raw[position : position + size]
            position += size
        else:
            raise ValueError("MRV 包含不支持的 Protobuf wire type")
        yield number, wire, value


def parse_mrv(raw):
    if len(raw) > 32 * 1024**2:
        raise ValueError("回放超过32MB")
    metadata, stats, frames = {}, {}, []
    for number, wire, value in _fields(raw):
        if number in range(1, 7) and wire == 2:
            if len(value) > 65536:
                raise ValueError("MRV 字符串过长")
            metadata[number] = value.decode("utf-8")
        elif number == 8 and wire == 2:
            stats = {n: v for n, w, v in _fields(value)}
        elif number == 9 and wire == 2:
            frames.append(value)
            if len(frames) > 1000000:
                raise ValueError("MRV 事件过多")
    md5 = metadata.get(5, "").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", md5) or not stats or not frames:
        raise ValueError("不是已核验的 Malody V MRV 回放")
    # The user verified this exact combination: PC, Const + LN-to-note, 1.0x.
    # Its individual bits are not inferred from the older MR format.
    mods = stats.get(2, 0)
    if mods != 16392:
        raise ValueError(f"此 MRV Mod 设置尚未核验（{mods}），请提供该设置的样本")
    presses, releases, judgements = [], [], []
    result_codes = {1: "miss", 2: "perfect", 4: "great", 8: "good"}
    previous = -1
    for frame in frames:
        timestamp, payloads = 0, []
        for n, w, value in _fields(frame):
            if n == 1 and w == 0:
                timestamp = value
            elif n == 3 and w == 2:
                payloads.append(value)
        if timestamp > 2**31 - 1:
            continue  # signed negative pre-play time
        if timestamp < previous:
            raise ValueError("MRV 时间顺序不合法")
        previous = timestamp
        current = None
        for payload in payloads:
            for n, w, value in _fields(payload):
                if n in (1, 2) and w == 0:
                    if not 0 <= value < 10:
                        raise ValueError("MRV 按键轨道超出范围")
                    (presses if n == 1 else releases).append(
                        {"time": timestamp, "key": value}
                    )
                elif n == 31 and w == 2:
                    judge = {a: v for a, b, v in _fields(value)}
                    key, code = judge.get(1, 0), judge.get(3, 0) & 31
                    if key >= 10 or code not in result_codes:
                        raise ValueError("MRV 包含尚未核验的判定类型")
                    current = {
                        "time": timestamp,
                        "key": key,
                        "result": result_codes[code],
                    }
                    judgements.append(current)
                elif n == 42 and w == 0 and current is not None:
                    current["combo"] = value
                elif n == 43 and w == 5 and current is not None:
                    accuracy = struct.unpack("<f", value)[0]
                    if not math.isfinite(accuracy) or not 0 <= accuracy <= 100:
                        raise ValueError("MRV 准确率不合法")
                    current["accuracy"] = accuracy
    counts = {
        "perfect": stats.get(7, 0),
        "great": stats.get(8, 0),
        "good": stats.get(9, 0),
        "miss": stats.get(10, 0),
        "ok": 0,
        "meh": 0,
    }
    for result, expected in counts.items():
        if sum(row["result"] == result for row in judgements) != expected:
            raise ValueError("MRV 逐次判定与成绩头部不一致")
    if not presses or any("combo" not in row for row in judgements):
        raise ValueError("MRV 缺少按键或连击快照")
    return {
        "source": "malody",
        "format": "mrv",
        "md5": md5,
        "title": metadata.get(1, ""),
        "difficulty": metadata.get(4, ""),
        "username": metadata.get(6, ""),
        "score": stats.get(5, 0),
        "max_combo": stats.get(6, 0),
        "mods": mods,
        "mirror": False,
        "rate": 1.0,
        "constant_scroll": True,
        "holds_to_notes": True,
        "presses": presses,
        "releases": releases,
        "press_count": len(presses),
        "counts": counts,
        "recorded_judgements": judgements,
        "windows": [52, 92, 126, 150],
        "classic": False,
    }
