"""Regression test for the two `(256, -500)` marker frames at the head of an `.osr`.

The bug: `parse_osr` dropped those two frames with `continue` BEFORE `t += w`, so their
deltas never reached the clock. osu! does the opposite — `LegacyScoreDecoder.readLegacyReplay`
accumulates every frame's delta (`lastTime += diff;`) and only *then* removes the markers
(`legacyFrames.RemoveAt(1)` / `RemoveAt(0)`).

The second marker's delta is normally **-1 ms**, so dropping it is invisible; but a real
2026-09-30 user render carried **5630 ms** there, which put that replay's entire press
stream 5.63 s early — the HUD read 31.60 % against a 99.12 % score.

What this test pins:
  * the marker frames contribute their deltas to the clock, and are still not turned into
    key presses/releases;
  * with the markers' deltas honoured, a press's time does not depend on the marker delta;
    with them dropped it is wrong by exactly that delta (so the test is red-capable);
  * the parse matches an independent re-implementation of osu!'s own accumulation;
Optional: if the real user replay is present in `cache/osr`, its parsed first press is
checked against the value measured on 2026-09-30.

Run: python tools/test_osr_sentinel.py
"""
from __future__ import annotations

import lzma
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mania_render.osr import parse_osr  # noqa: E402

FAILS: list[str] = []
REAL_OSR = (Path(__file__).resolve().parents[1]
            / "cache" / "osr" / "8c78d4628d5d49e48cd51099b1cd80fd_replay.osr")
REAL_FIRST_PRESS = 6987          # measured 2026-09-30 with the marker delta honoured
REAL_DROPPED_FIRST_PRESS = 1357  # what the old parse produced for the same file


def check(name: str, got, want) -> None:
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got {got!r} want {want!r}")
    if not ok:
        FAILS.append(name)


def _uleb(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def build_osr(frame_text: str, mods: int = 0) -> bytes:
    """Minimal but structurally valid mania .osr carrying `frame_text` verbatim."""
    blob = lzma.compress(frame_text.encode(), format=lzma.FORMAT_ALONE)
    out = bytearray()
    out += bytes([3])                             # ruleset: mania
    out += struct.pack("<i", 20260101)            # version
    for s in ("0" * 32, "Tester", "0" * 32):      # beatmap md5, player, replay md5
        b = s.encode()
        out += bytes([0x0B]) + _uleb(len(b)) + b
    out += struct.pack("<6h", 0, 0, 0, 0, 0, 0)   # counts
    out += struct.pack("<i", 100000)              # score
    out += struct.pack("<h", 1)                   # max combo
    out += bytes([0])                             # perfect
    out += struct.pack("<i", mods)                # mods
    out += bytes([0x00])                          # life (empty string)
    out += struct.pack("<q", 0)                   # timestamp
    out += struct.pack("<i", len(blob)) + blob
    return bytes(out)


def frames_with_marker(delta: int) -> str:
    """Two marker frames, then a real head that steps back to t=0 and presses key 0 at 30 ms.

    `delta` only ever appears on the marker; with the marker's delta counted the press is at
    30 ms whatever `delta` is, and with it dropped the press is at 30 - delta.
    """
    return ",".join([
        "0|256|-500|0",
        f"{delta}|256|-500|0",
        f"{-delta}|0|8.5|0",
        "30|0|8.5|0",
        "0|1|8.5|0",        # key 0 down at t = 30
        "10|0|8.5|0",       # key 0 up   at t = 40
        "-12345|0|0|10700069",
    ])


def parse_frames(frame_text: str):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "r.osr"
        p.write_bytes(build_osr(frame_text))
        _, rep = parse_osr(p)
    return rep


def _split(frame_text: str):
    """(absolute time, key mask, is_marker) per frame, deltas accumulated for EVERY frame."""
    import math
    t = 0
    out = []
    for fr in frame_text.split(","):
        fr = fr.strip()
        if not fr:
            continue
        parts = fr.split("|")
        if len(parts) < 4:
            continue
        if parts[0] == "-12345":                     # rng-seed trailer
            continue
        t += int(float(parts[0]))
        x = int(float(parts[1]))
        y = int(round(float(parts[2])))
        out.append((t, x, y, x == 256 and y == -500))
    return out


def reference_times(frame_text: str, honour_marker_delta: bool = True):
    """osu!'s own reading, re-implemented independently of mania_render/osr.py.

    `honour_marker_delta=False` reproduces the old renderer behaviour (delta dropped along
    with the frame) so the test can prove it is red-capable.
    """
    frames = []
    if honour_marker_delta:
        frames = [(t, x, marker) for (t, x, _y, marker) in _split(frame_text)]
    else:
        t = 0
        for fr in frame_text.split(","):
            fr = fr.strip()
            if not fr:
                continue
            parts = fr.split("|")
            if len(parts) < 4 or parts[0] == "-12345":
                continue
            x = int(float(parts[1]))
            y = int(round(float(parts[2])))
            if x == 256 and y == -500:
                continue
            t += int(float(parts[0]))
            frames.append((t, x, True and False))
    if len(frames) >= 2 and frames[1][2]:
        del frames[1]
    if len(frames) >= 1 and frames[0][2]:
        del frames[0]
    presses = []
    for i in range(1, len(frames)):
        mask_prev, mask_cur = frames[i - 1][1] & 0xFFFFF, frames[i][1] & 0xFFFFF
        for bit in range(20):
            if not (mask_prev >> bit) & 1 and (mask_cur >> bit) & 1:
                presses.append((frames[i][0], bit))
    return presses


def main() -> int:
    print("marker frames: deltas count, frames do not become inputs")
    # NB: -12345 is reserved (rng-seed trailer) and is skipped by both readers, so it is not
    # a usable marker delta here — 9000 stands in for "any other large value".
    for delta in (-1, 0, 5630, 9000):
        text = frames_with_marker(delta)
        rep = parse_frames(text)
        check(f"delta={delta}: presses match osu!'s own accumulation",
              [(p.time_ms, p.column) for p in rep.presses], reference_times(text))
        check(f"delta={delta}: press time is independent of the marker delta",
              rep.presses[0].time_ms, 30)
        check(f"delta={delta}: exactly one press / one release",
              (len(rep.presses), len(rep.releases)), (1, 1))
        check(f"delta={delta}: the marker frames emit no key events of their own",
              [p.column for p in rep.presses], [0])

    print("the test is red-capable: the old behaviour is wrong by exactly the marker delta")
    for delta in (-1, 5630, 9000):
        text = frames_with_marker(delta)
        old = reference_times(text, honour_marker_delta=False)
        fixed = reference_times(text, honour_marker_delta=True)
        check(f"delta={delta}: dropping the delta moves the press by -{delta}",
              old[0][0] - fixed[0][0], -delta)
        check(f"delta={delta}: and the shipped parser agrees with the fixed reference",
              parse_frames(text).presses[0].time_ms, fixed[0][0])
    check("delta=0 is indistinguishable (why -1 ms hid this for so long)",
          reference_times(frames_with_marker(0), honour_marker_delta=False)[0][0],
          reference_times(frames_with_marker(0), honour_marker_delta=True)[0][0])

    print("real replay from the 2026-09-30 report")
    if REAL_OSR.exists():
        _, rep = parse_osr(REAL_OSR)
        check("first press (marker delta honoured)", rep.presses[0].time_ms, REAL_FIRST_PRESS)
        check("first press is not the old, 5.63 s-early value",
              rep.presses[0].time_ms != REAL_DROPPED_FIRST_PRESS, True)
        check("press count", len(rep.presses), 1364)
    else:
        print(f"  SKIP  {REAL_OSR} not present")

    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): " + ", ".join(FAILS))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
