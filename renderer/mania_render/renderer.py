from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .hud import HudState, build_fc_sim, build_from_replay, hud_state_at
from .models import ANCHOR_POINT, OsuBeatmap, ReplayData, SerialisedDrawable
from .playfield import VIEW_H, VIEW_W, PlayfieldGeometry, y_for_time
from .skin import (
    DEFAULT_LAYOUT,
    ROLE_ACCURACY,
    ROLE_ATTRIBUTE,
    ROLE_BAR_ERROR,
    ROLE_BPM,
    ROLE_COMBO,
    ROLE_CPS,
    ROLE_SONG_PROGRESS,
    LoadedSkin,
)

VIEW = (VIEW_W, VIEW_H)


def _find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    candidates = [
        r"D:\ComfyUI\ComfyUI_Windows_portable\python_standalone\Scripts\ffmpeg.exe",
        r"D:\OOPZ\oopz\ffmpeg.exe",
        r"D:\LLBot\bin\llbot\ffmpeg.exe",
    ]
    # prefer known-good mp4 muxers first
    for p in candidates:
        if Path(p).is_file():
            return p
    if exe:
        return exe
    raise RuntimeError("ffmpeg not found")


def _load_font(size: int) -> ImageFont.ImageFont:
    # Windows first (the dev box), then the usual Linux/macOS locations — on a Linux server
    # the old three-entry list fell straight through to `load_default()`, a tiny bitmap
    # face that made every HUD readout the wrong size.
    for name in (
        "C:/Windows/Fonts/SegoeUI.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        if Path(name).is_file():
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _anchor_xy(anchor: int) -> tuple[float, float]:
    fx, fy = ANCHOR_POINT.get(anchor, (0.0, 0.0))
    return fx * VIEW_W, fy * VIEW_H


def _origin_offset(origin: int, w: float, h: float) -> tuple[float, float]:
    fx, fy = ANCHOR_POINT.get(origin, (0.0, 0.0))
    return -fx * w, -fy * h


def _fit(img: Image.Image, box_w: float, scale: float) -> Image.Image:
    tw = max(1, int(img.width * scale))
    th = max(1, int(img.height * scale))
    return img.resize((tw, th), Image.Resampling.BILINEAR)


def _colorkey_black(img: Image.Image, thresh: int = 24) -> Image.Image:
    """Make near-black opaque pixels transparent (Cho noteT/noteL have opaque black bg)."""
    arr = np.array(img)
    mask = (arr[:, :, 0] < thresh) & (arr[:, :, 1] < thresh) & (arr[:, :, 2] < thresh) & (arr[:, :, 3] > 0)
    arr[mask, 3] = 0
    return Image.fromarray(arr, "RGBA")


# ── ProcessPoolExecutor worker (module-level for pickling on Windows spawn) ──
_WR: Renderer | None = None


def _init_render_worker(r: "Renderer") -> None:  # noqa: F821
    global _WR
    _WR = r


def _render_frame_task(args: tuple) -> tuple[int, bytes, tuple, bool]:
    i, now_ms = args
    r = _WR
    assert r is not None
    st = hud_state_at(r.events, r.bm, now_ms, r._length_s)
    hud_key = (int(st.time_s), st.combo, int(st.accuracy * 10), len(st.clicks_window), round(st.bpm))
    idle = r._is_playfield_idle(now_ms)
    img = r.render_frame(now_ms)
    # numpy drop-alpha → bytes (avoids PIL convert round-trip)
    arr = np.asarray(img)
    raw = np.ascontiguousarray(arr[:, :, :3]).tobytes()
    return i, raw, hud_key, idle


def _blit_rgba(base: Image.Image, img: Image.Image, x: int, y: int) -> None:
    base.alpha_composite(img, (int(x), int(y)))


def _blit_additive(base: Image.Image, img: Image.Image, x: int, y: int, alpha: float = 1.0) -> None:
    """Lazer lighting uses additive blending. Only touch the overlapping rect."""
    if alpha <= 0:
        return
    x, y = int(x), int(y)
    bw, bh = base.size
    iw, ih = img.size
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(bw, x + iw), min(bh, y + ih)
    if x1 <= x0 or y1 <= y0:
        return
    src = img
    if alpha < 1.0:
        src = img.copy()
        a = src.getchannel("A").point(lambda v: int(v * alpha))
        src.putalpha(a)
    crop = src.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    region = base.crop((x0, y0, x1, y1))
    # fast path: PIL additive (correct for opaque/fully-transparent sprites)
    from PIL import ImageChops

    rgb = ImageChops.add(region.convert("RGB"), crop.convert("RGB"))
    out = rgb.convert("RGBA")
    out.putalpha(region.getchannel("A"))
    base.paste(out, (x0, y0))


def _draw_text_center(
    img: Image.Image,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill=(255, 255, 255, 255),
    origin: int = 9,
    align: str = "left",
) -> None:
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    ox, oy = _origin_offset(origin, w, h)
    x, y = xy[0] + ox, xy[1] + oy
    if align == "right":
        x = xy[0] - w + ox
    draw.text((x, y), text, font=font, fill=fill)


class Renderer:
    def __init__(
        self,
        bm: OsuBeatmap,
        audio_path: Path,
        skin: LoadedSkin,
        geom: PlayfieldGeometry,
        *,
        scroll_speed: float = 30.0,
        fps: int = 60,
        hit_effects: bool = True,
        background: bool = True,
        bg_path: Path | None = None,
        replay: ReplayData | None = None,
        bg_dim: float = 0.6,
    ) -> None:
        self.bm = bm
        self.audio_path = audio_path
        self.skin = skin
        self.geom = geom
        self.fps = fps
        self.hit_effects = hit_effects
        self.draw_background = background
        self.bg_path = bg_path
        self.replay = replay
        self.scroll_speed = scroll_speed
        # 0 = background at full strength, 1 = black. lazer dims the beatmap background
        # behind the playfield; 0.6 is what this renderer has always used.
        self.bg_dim = min(1.0, max(0.0, float(bg_dim)))

        self.events = build_from_replay(bm, replay) if replay else build_fc_sim(bm)
        self.font_s = _load_font(22)
        self.font_m = _load_font(28)
        self.font_l = _load_font(40)

        self._bg_cache: Image.Image | None = None
        self._note_cache: dict[tuple, Image.Image] = {}
        self._scaled_cache: dict[tuple, Image.Image] = {}
        self._cache_lock = threading.Lock()
        self._static_cache: Image.Image | None = None
        self._error_trail: list[tuple[int, float]] = []
        self._length_s = 1.0
        self.star_text = ""
        # hit objects sorted for windowed draw
        self._objs = sorted(self.bm.hit_objects, key=lambda h: h.start_time)
        self._obj_starts = [h.start_time for h in self._objs]
        # press events sorted for windowed lighting (FC/replay)
        self._presses = sorted(
            ((t, col) for col, holds in self.events.key_held.items() for t, _ in holds),
            key=lambda p: p[0],
        )
        self._press_times = [p[0] for p in self._presses]
        self._holds_sorted = sorted(
            ((a, b, col) for col, holds in self.events.key_held.items() for a, b in holds if b > a),
            key=lambda x: x[0],
        )
        self._hold_starts = [x[0] for x in self._holds_sorted]
        # window must cover long holds (end_time far past start_time)
        self._max_hold_ms = 1
        for h in self.bm.hit_objects:
            if h.is_hold:
                self._max_hold_ms = max(self._max_hold_ms, h.end_time - h.start_time)

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop("_cache_lock", None)
        state.pop("font_s", None)
        state.pop("font_m", None)
        state.pop("font_l", None)
        state.pop("_static_bytes", None)  # rebuilt per worker from _static_cache
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._cache_lock = threading.Lock()
        self.font_s = _load_font(22)
        self.font_m = _load_font(28)
        self.font_l = _load_font(40)

    def _background(self) -> Image.Image:
        if not self.draw_background:
            return Image.new("RGBA", VIEW, (12, 12, 16, 255))
        if self._bg_cache is not None:
            return self._bg_cache.copy()
        img = Image.new("RGBA", VIEW, (12, 12, 16, 255))
        # `bg_dim` 0..1 -> alpha 0..255. A zero-alpha overlay would still be composited
        # (a no-op), so it is skipped outright when the caller asked for no dimming.
        dim_a = int(round(self.bg_dim * 255))
        dim = Image.new("RGBA", VIEW, (0, 0, 0, dim_a)) if dim_a > 0 else None
        if self.bg_path and self.bg_path.is_file():
            try:
                src = Image.open(self.bg_path).convert("RGBA")
                scale = max(VIEW_W / src.width, VIEW_H / src.height)
                src = src.resize((int(src.width * scale), int(src.height * scale)), Image.Resampling.BILINEAR)
                left = (src.width - VIEW_W) // 2
                top = (src.height - VIEW_H) // 2
                src = src.crop((left, top, left + VIEW_W, top + VIEW_H))
                if dim is not None:
                    src.alpha_composite(dim)
                img = src
            except Exception:
                pass
        else:
            # try skin texture as fallback art
            for key in ("menu-background", "menu-background-2x"):
                t = self.skin.textures.get(key)
                if t:
                    scale = max(VIEW_W / t.width, VIEW_H / t.height)
                    t = t.resize((int(t.width * scale), int(t.height * scale)), Image.Resampling.BILINEAR)
                    left = (t.width - VIEW_W) // 2
                    top = (t.height - VIEW_H) // 2
                    t = t.crop((left, top, left + VIEW_W, top + VIEW_H))
                    if dim is not None:
                        t.alpha_composite(dim)
                    img = t
                    break
        self._bg_cache = img
        return img.copy()

    def _note_height_px(self, col: int) -> float:
        """Lazer LegacyNotePiece: height from WidthForNoteHeightScale (768-space) * view scale."""
        block = self.skin.block_for_keys(self.geom.keys)
        w768 = 0.0
        if block and block.column_width and col < len(block.column_width):
            w768 = block.column_width[col]
        ref = (block.width_for_note_height if block and block.width_for_note_height else w768) or w768
        if ref <= 0:
            ref = 48.0
        return max(8.0, ref * self.geom.scale)

    def _scaled(self, img: Image.Image, col: int, height: float | None = None) -> Image.Image:
        """LegacyNotePiece: scale = (DrawWidth, noteHeight) / texture.DisplayWidth."""
        w = max(2, int(self.geom.col_w[col] - 2))
        ref = height if height is not None else self._note_height_px(col)
        tw, th = img.size
        if tw <= 0:
            tw = 1
        # A 1-2px dimension is osu!'s "stretch me" idiom (boj's LN tail is 128x1, its body
        # 128x40000). Running those through the aspect formula collapsed the tail to the
        # 4px floor — a sliver nobody can see. Such a sprite takes the target size instead.
        if th <= 2 or tw <= 2:
            h = max(4, int(ref))
        else:
            h = max(4, int(th * ref / tw))
        key = (id(img), w, h)
        with self._cache_lock:
            hit = self._scaled_cache.get(key)
        if hit is not None:
            return hit
        out = img.resize((w, h), Image.Resampling.BILINEAR)
        with self._cache_lock:
            self._scaled_cache[key] = out
        return out

    def _note_sprite(self, col: int, kind: str) -> Image.Image | None:
        key = (col, kind)
        with self._cache_lock:
            if key in self._note_cache:
                return self._note_cache[key]
        block = self.skin.block_for_keys(self.geom.keys)
        name = None
        if block and col in block.note_images:
            name = block.note_images[col].get(kind)
        if not name:
            # LegacyManiaColumnElement.FallbackColumnIndex
            # special → S; else distanceToEdge % 2 → "1" / "2"
            n_keys = self.geom.keys
            col_in_stage = col
            if n_keys >= 10:
                bank = "S"
            else:
                dist = min(col_in_stage, (n_keys - 1) - col_in_stage)
                bank = "1" if (dist % 2 == 0) else "2"
            suffix = {"body": "", "head": "H", "hold": "L", "tail": "T"}[kind]
            name = f"mania-note{bank}{suffix}"
        img = self.skin.textures.get(name)
        if img is None and kind != "body":
            img = self.skin.textures.get(name[:-1] if name else None) or self.skin.textures.get(
                name.replace("H", "").replace("L", "").replace("T", "") if name else None
            )
        if img is None:
            w = int(self.geom.col_w[col] - 2)
            h = 14 if kind != "hold" else 32
            img = Image.new("RGBA", (max(4, w), h), (220, 220, 230, 255))
        elif kind in ("tail", "hold"):
            img = _colorkey_black(img.copy())
        with self._cache_lock:
            self._note_cache[key] = img
        return img

    def _static_stage(self) -> Image.Image:
        """Bg + columns + keys + hint (no notes) — built once per renderer."""
        if self._static_cache is not None:
            return self._static_cache
        g = self.geom
        frame = self._background()
        draw = ImageDraw.Draw(frame, "RGBA")
        block = self.skin.block_for_keys(g.keys)
        left = self.skin.textures.get("mania-stage-left")
        right = self.skin.textures.get("mania-stage-right")
        stage_h = VIEW_H
        if left:
            li = left.resize((max(2, int(left.width * g.scale)), stage_h), Image.Resampling.BILINEAR)
            _blit_rgba(frame, li, int(g.stage_left - li.width), 0)
        if right:
            ri = right.resize((max(2, int(right.width * g.scale)), stage_h), Image.Resampling.BILINEAR)
            _blit_rgba(frame, ri, int(g.stage_right), 0)
        for i in range(g.keys):
            x0 = g.col_x[i]
            w = g.col_w[i]
            draw.rectangle([x0, 0, x0 + w, VIEW_H], fill=(0, 0, 0, 120))
        for i in range(g.keys):
            x0 = g.col_x[i]
            w = g.col_w[i]
            name = None
            if block and i in block.key_images:
                name = block.key_images[i].get("up")
            if not name:
                name = "mania-key1" if i % 2 == 0 else "mania-key2"
            key_img = self.skin.textures.get(name) or self.skin.textures.get("mania-keys")
            ky = int(g.hit_y)
            if key_img:
                ki = key_img.resize((max(2, int(w)), max(4, int(key_img.height * g.scale))), Image.Resampling.BILINEAR)
                # The receptor's CENTRE sits on the judgement line (confirmed against the
                # game). Anchoring it to the bottom of the playfield instead put it 81px
                # high at HitPosition 432, so a held LN's head looked like it hung below
                # its own key.
                _blit_rgba(frame, ki, int(x0), int(ky - ki.height / 2))
            else:
                draw.rectangle([x0, ky, x0 + w, ky + 8], fill=(240, 240, 240, 200))
        # Judgement line + hit target (lazer LegacyHitTarget / LegacyStageForeground).
        # `StageHint` overrides `mania-stage-hint`, and the sprite is drawn with
        # Scale.y = 0.9 * 1.6025 — the 1.6025 is the 480→768 legacy conversion lazer
        # applies on top of the texture's own height. The separate 1px white bar is the
        # `JudgementLine` toggle, which skins routinely turn off (`JudgementLine: 0`).
        hint_name = (getattr(block, "stage_hint", "") or "mania-stage-hint")
        hint = self.skin.textures.get(hint_name)
        if hint:
            hi = hint.resize(
                (int(g.stage_right - g.stage_left),
                 max(2, int(hint.height * g.scale * (0.9 * 1.6025)))),
                Image.Resampling.BILINEAR,
            )
            _blit_rgba(frame, hi, int(g.stage_left), int(g.hit_y - hi.height / 2))
        if block is None or block.judgement_line:
            draw.rectangle([g.stage_left, g.hit_y - 2, g.stage_right, g.hit_y + 2], fill=(255, 255, 255, 220))
        self._static_cache = frame
        return frame

    def _compose_stage(self, frame: Image.Image, now_ms: float) -> None:
        g = self.geom
        draw = ImageDraw.Draw(frame, "RGBA")

        # pressed receptors (static cache has idle KeyImage; overlay down state)
        block = self.skin.block_for_keys(g.keys)
        for i in range(g.keys):
            holds = self.events.key_held.get(i, [])
            held = any(a <= now_ms <= b for a, b in holds)
            if not held:
                continue
            name = None
            if block and i in block.key_images:
                name = block.key_images[i].get("down")
            if not name:
                name = "mania-key1d" if i % 2 == 0 else "mania-key2d"
            key_img = self.skin.textures.get(name) or self.skin.textures.get("mania-keysd")
            if key_img:
                ki = key_img.resize((max(2, int(g.col_w[i])), max(4, int(key_img.height * g.scale))), Image.Resampling.BILINEAR)
                # same centre-on-the-judgement-line anchor as the idle sprite
                _blit_rgba(frame, ki, int(g.col_x[i]), int(g.hit_y - ki.height / 2))

        # windowed hit objects — span must include max LN length or long holds vanish mid-body
        from bisect import bisect_left, bisect_right

        span = self.geom.time_range * 3 + self._max_hold_ms
        lo = bisect_left(self._obj_starts, now_ms - span)
        hi = bisect_right(self._obj_starts, now_ms + span)
        for h in self._objs[lo:hi]:
            col = h.column
            if col < 0 or col >= g.keys:
                continue
            x0 = g.col_x[col] + 1
            w = g.col_w[col] - 2
            nh = self._note_height_px(col)
            y1 = y_for_time(g, h.start_time, now_ms)
            y2 = y_for_time(g, h.end_time, now_ms) if h.is_hold else y1

            if not g.upside_down:
                if h.is_hold:
                    if now_ms >= h.end_time:
                        continue
                    # WebGL models an LN as two layers: body + tail inside a mask whose
                    # bottom edge is `judgement line - Head.Height/2`, and the head OUTSIDE
                    # that mask, painted last, for the whole hold (`nowMs <= t2`).
                    #
                    # Both halves of that matter. Without the mask the body runs to the
                    # judgement line and paints over the receptor. And folding the head
                    # into the masked block was worse: the block bails out as soon as the
                    # tail is above the mask, so the head vanished with it — the whole LN
                    # blinked out ~110px before its tail ever reached the line.
                    mask_bot = g.hit_y - nh / 2.0
                    y_tail = y2
                    y_head = y1

                    def _cap(slot: str, y_pt: float, flip_v: bool = False,
                             bottom_align: bool = False) -> None:
                        img = self._note_sprite(col, slot) or self._note_sprite(col, "body")
                        if not img:
                            return
                        if flip_v:
                            img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                        ci = self._scaled(img, col, nh)
                        y = (y_pt - ci.height) if bottom_align else (y_pt - ci.height / 2)
                        _blit_rgba(frame, ci, int(x0), int(y))

                    # ── inside the mask: body + tail ──
                    if y_tail <= mask_bot + 1:
                        bot = mask_bot if now_ms >= h.start_time else y_head
                        if bot > mask_bot:
                            bot = mask_bot
                        top = y_tail if y_tail >= 0 else 0.0
                        if bot > top:
                            body = self._note_sprite(col, "hold")
                            if body:
                                bh = max(2, int(bot - top))
                                bkey = (col, "hold", bh)
                                bi = self._scaled_cache.get(bkey)
                                if bi is None:
                                    bi = body.resize((max(2, int(w)), bh),
                                                     Image.Resampling.BILINEAR)
                                    self._scaled_cache[bkey] = bi
                                _blit_rgba(frame, bi, int(x0), int(top))
                            tail_top = min(y_tail, mask_bot)
                            # osu LegacyHoldNoteTailPiece: direction inverted → Scale Y=-1
                            # (flip); the sprite's bottom edge sits at the tail's position.
                            _cap("tail", tail_top, flip_v=True, bottom_align=True)

                    # ── outside the mask, painted last: the head STAYS for the whole hold ──
                    _cap("head", min(y_head, g.hit_y))
                else:
                    if now_ms >= h.start_time:
                        continue  # judged / gone
                    # LegacyNotePiece sets `Origin = Anchor.BottomCentre`, so the sprite's
                    # BOTTOM edge sits at its time position — it is not centred on it.
                    # Centring here drew every note half a note-height too high.
                    if y1 >= g.hit_y or y1 + nh < 0:
                        continue
                    body = self._note_sprite(col, "body")
                    if body:
                        bi = self._scaled(body, col, nh)
                        _blit_rgba(frame, bi, int(x0), int(y1 - bi.height))
            else:
                if h.is_hold:
                    if now_ms >= h.end_time:
                        continue
                    top = g.hit_y if now_ms >= h.start_time else y1
                    bot = y2
                    if bot < g.hit_y - 1:
                        continue
                    if top < g.hit_y:
                        top = g.hit_y
                    if bot < top:
                        continue
                    body = self._note_sprite(col, "hold")
                    if body:
                        bh = max(2, int(bot - top))
                        bi = body.resize((max(2, int(w)), bh), Image.Resampling.BILINEAR)
                        _blit_rgba(frame, bi, int(x0), int(top))
                    tail = self._note_sprite(col, "tail") or self._note_sprite(col, "head") or self._note_sprite(col, "body")
                    if tail and bot > g.hit_y:
                        ti = self._scaled(tail, col, nh)
                        _blit_rgba(frame, ti, int(x0), int(y2 - nh / 2))
                    if now_ms < h.start_time:
                        head = self._note_sprite(col, "head") or self._note_sprite(col, "body")
                        if head:
                            hi = self._scaled(head, col, nh)
                            _blit_rgba(frame, hi, int(x0), int(y1 - nh / 2))
                else:
                    if now_ms >= h.start_time:
                        continue
                    if y1 < g.hit_y or y1 > VIEW_H + 40:
                        continue
                    body = self._note_sprite(col, "body")
                    if body:
                        bi = self._scaled(body, col, nh)
                        _blit_rgba(frame, bi, int(x0), int(y1 - nh / 2))

        # hit lighting: lightingN on press (200ms), lightingL while holding
        if self.hit_effects:
            self._draw_lighting(frame, now_ms)

    def _lighting_frames(self, base: str) -> list[Image.Image]:
        """Collect lightingN / lightingL frames (lightingN-0, lightingN-1, ... or lightingN)."""
        key = base.lower()
        frames: list[Image.Image] = []
        # multi-frame animation
        i = 0
        while True:
            img = self.skin.textures.get(f"{key}-{i}")
            if img is None:
                break
            frames.append(img)
            i += 1
            if i > 32:
                break
        if frames:
            return frames
        single = self.skin.textures.get(key)
        return [single] if single else []

    def _draw_lighting(self, frame: Image.Image, now_ms: float) -> None:
        g = self.geom
        block = self.skin.block_for_keys(g.keys)
        default_col = 48.0

        n_frames = self._lighting_frames("lightingn")
        l_frames = self._lighting_frames("lightingl")
        # skin.ini LightingN/L may rename (e.g. Cho: lightingA)
        block = self.skin.block_for_keys(self.geom.keys)
        if block:
            if getattr(block, "lighting_n", ""):
                n_frames = self._lighting_frames(block.lighting_n) or n_frames
            if getattr(block, "lighting_l", ""):
                l_frames = self._lighting_frames(block.lighting_l) or l_frames

        # empty skin lighting (maxA==0) → nothing to draw (owc case)
        def _visible(img: Image.Image) -> bool:
            try:
                return img.getbbox() is not None
            except Exception:
                return True

        n_frames = [f for f in n_frames if _visible(f)]
        l_frames = [f for f in l_frames if _visible(f)]
        if not n_frames and not l_frames:
            return

        def _scale(col: int, widths: list[float]) -> float:
            if block and col < len(widths):
                w = widths[col] or 0.0
                if w > 0:
                    return max(0.3, w / default_col)
            return max(0.5, g.col_w[col] / max(1.0, default_col * g.scale))

        from bisect import bisect_left, bisect_right

        # lighting sprites: size/position follow the PNG (user), scaled by LightingNWidth
        n_frames = self._lighting_frames("lightingn")
        l_frames = self._lighting_frames("lightingl")
        if block:
            if getattr(block, "lighting_n", ""):
                n_frames = self._lighting_frames(block.lighting_n) or n_frames
            if getattr(block, "lighting_l", ""):
                l_frames = self._lighting_frames(block.lighting_l) or l_frames
        # drop 1x1 / empty placeholders
        n_frames = [f for f in n_frames if f.width >= 2 and f.height >= 2 and (f.getbbox() is not None)]
        l_frames = [f for f in l_frames if f.width >= 2 and f.height >= 2 and (f.getbbox() is not None)]
        if not n_frames and not l_frames:
            return

        def _png_scale(col: int, widths: list[float], img: Image.Image) -> float:
            """LightingNWidth[col]/DEFAULT_COLUMN_SIZE, fallback fit to column."""
            if block and col < len(widths):
                w = widths[col] or 0.0
                if w > 0:
                    return max(0.25, w / default_col)
            return max(0.25, g.col_w[col] / max(1.0, default_col * g.scale))

        def _blit_png(frame: Image.Image, img: Image.Image, col: int, widths: list[float], alpha: float) -> None:
            # size follows the PNG: LightingNWidth[col]/DEFAULT_COLUMN_SIZE * natural size
            sc = _png_scale(col, widths, img)
            w = max(4, int(img.width * sc))
            h = max(4, int(img.height * sc))
            key = (id(img), w, h)
            spr = self._scaled_cache.get(key)
            if spr is None:
                spr = img.resize((w, h), Image.Resampling.BILINEAR)
                self._scaled_cache[key] = spr
            cx = g.col_x[col] + g.col_w[col] / 2.0
            # osu: Origin=Centre + Anchor=BottomCentre → sprite CENTRE on hit line
            _blit_additive(frame, spr, cx - w / 2.0, g.hit_y - h / 2.0, max(0.0, min(1.0, alpha)))

        from bisect import bisect_left, bisect_right

        def _explosion_frame(age: float, n: int) -> int:
            # LegacyHitExplosion: frameLength = max(1000/60, 170/FrameCount)
            fl = max(1000.0 / 60.0, 170.0 / max(1, n))
            return min(n - 1, int(age / fl))

        # lightingL FIRST (hold glow at hit line), then lightingN on top
        # LegacyBodyPiece: FadeIn(80) / FadeOut(120), additive, centre on hit line
        if l_frames and self._holds_sorted:
            lo = bisect_left(self._hold_starts, now_ms - 10_000)
            for a, b, col in self._holds_sorted[lo:]:
                if a > now_ms:
                    break
                if col < 0 or col >= g.keys:
                    continue
                if now_ms < a - 1:
                    continue
                if now_ms <= b:
                    age_in = now_ms - a
                    alpha = min(1.0, age_in / 80.0) if age_in < 80 else 1.0
                else:
                    age_out = now_ms - b
                    if age_out > 120:
                        continue
                    alpha = 1.0 - age_out / 120.0
                fl = max(1000.0 / 60.0, 170.0 / max(1, len(l_frames)))
                age_cycle = (now_ms - a) % max(1.0, len(l_frames) * fl)
                fi = min(len(l_frames) - 1, int(age_cycle / fl))
                _blit_png(frame, l_frames[fi], col, getattr(block, "hold_light_width", []) or [], alpha)

        # lightingN: presses in [now-200, now] — LegacyHitExplosion.Animate
        #   FadeInFromZero(80) then FadeOut(120) = 200ms total
        if n_frames:
            lo = bisect_left(self._press_times, now_ms - 200)
            hi = bisect_right(self._press_times, now_ms)
            for a, col in self._presses[lo:hi]:
                if col < 0 or col >= g.keys:
                    continue
                age = now_ms - a
                if age < 0 or age > 200:
                    continue
                if age < 80:
                    alpha = age / 80.0          # FadeInFromZero(80)
                else:
                    alpha = 1.0 - (age - 80) / 120.0  # FadeOut(120)
                fi = _explosion_frame(age, len(n_frames))
                _blit_png(frame, n_frames[fi], col, getattr(block, "explosion_width", []) or [], alpha)

    def _place(
        self,
        frame: Image.Image,
        item: SerialisedDrawable,
        st: HudState,
        now_ms: float,
        fallback_role: str | None = None,
    ) -> None:
        ax, ay = _anchor_xy(item.anchor)
        x, y = ax + item.x, ay + item.y
        # Role-specific drawing
        suffix = item.type_name.split(",")[0].rsplit(".", 1)[-1].lower()
        label_scale = item.scale_x or 1.0

        def text(s: str, font=None, origin=None, dy: float = 0.0) -> None:
            _draw_text_center(
                frame,
                (x, y + dy),
                s,
                font or self.font_m,
                origin=origin if origin is not None else item.origin,
            )

        if "combocounter" in suffix or fallback_role == ROLE_COMBO:
            text(f"{st.combo}x", self.font_l)
        elif "clickspersecond" in suffix or fallback_role == ROLE_CPS:
            text(f"{len(st.clicks_window)} clicks/sec", self.font_s)
        elif "songprogress" in suffix or fallback_role == ROLE_SONG_PROGRESS:
            total = st.length_s
            pct = 0.0 if total <= 0 else min(1.0, st.time_s / total)
            text(f"{int(st.time_s)}s / {int(total)}s ({pct*100:.0f}%)", self.font_s)
        elif "beatmapattribute" in suffix or fallback_role == ROLE_ATTRIBUTE:
            star = getattr(self, "star_text", "")
            text(star or f"Star: {self.bm.cs:.0f}K", self.font_s)
        elif "bpmcounter" in suffix or fallback_role == ROLE_BPM:
            bpm = st.bpm
            text(f"{bpm:.0f} BPM" if bpm else "BPM", self.font_s)
        elif "accuracycounter" in suffix or fallback_role == ROLE_ACCURACY:
            # TWO accuracy figures, unlabelled, SIDE BY SIDE on the one line the
            # skin gave this component: lazer's first (ScoreProcessor, where a
            # PERFECT is worth 305), then osu!stable's (Perfect and Great both
            # score 300 over a 300-per-judgement denominator).  They disagree on
            # every play that is not all-perfect, so both are shown.
            #
            # Side by side rather than stacked on purpose: the skin puts the
            # clicks-per-second counter 40px under this one, and a second line
            # above or below either ran into it or off the bottom edge.  Sharing
            # the baseline costs width instead of height, and this component is
            # right-anchored, so the extra width grows away from everything.
            text(f"{st.accuracy:.2f}% {st.accuracy_stable:.2f}%", self.font_m)
        elif "barhiterrormeter" in suffix or fallback_role == ROLE_BAR_ERROR:
            self._draw_error_bar(frame, item, x, y, now_ms)
        else:
            # extra components: minimal placeholder with type name
            short = suffix[:18]
            text(short, self.font_s)

    def _draw_replay_judgement_panel(self, frame: Image.Image, x: float, y: float, now_ms: float) -> None:
        """Left-centre panel (replay only): Ratio + MAX..0 + UR, live at now_ms."""
        from .hud import judge_counts, ratio_label, unstable_rate

        now = now_ms
        od = self.bm.od or 8.0
        counts = judge_counts(self.bm, self.events, od, now_ms=now)
        ur = unstable_rate(self.events, od, now_ms=now)
        draw = ImageDraw.Draw(frame, "RGBA")
        font = self.font_s
        font_big = self.font_m
        line_h = 28
        rows = [
            ("Ratio", ratio_label(counts), (255, 255, 255, 255), font_big),
            ("MAX", str(counts["max"]), (120, 230, 220, 255), font),
            ("300", str(counts["300"]), (245, 215, 80, 255), font),
            ("200", str(counts["200"]), (170, 210, 120, 255), font),
            ("100", str(counts["100"]), (240, 168, 104, 255), font),
            ("50", str(counts["50"]), (224, 108, 117, 255), font),
            ("0", str(counts["miss"]), (160, 160, 160, 255), font),
            ("UR", "—" if ur is None else f"{ur:.1f}", (220, 220, 230, 255), font_big),
        ]
        y0 = y - (len(rows) * line_h) / 2
        for i, (label, val, col, f) in enumerate(rows):
            yy = y0 + i * line_h
            draw.text((x, yy), label, font=font_big if label in ("Ratio", "UR") else font, fill=(200, 200, 210, 255))
            draw.text((x + 88, yy - (2 if label in ("Ratio", "UR") else 0)), val, font=f, fill=col)

    def _draw_error_bar(self, frame: Image.Image, item: SerialisedDrawable, x: float, y: float, now_ms: float) -> None:
        """Horizontal BarHitErrorMeter — lazer builds a vertical bar then Rotation=-90.

        Screen: early (δ<0) LEFT → 0 → RIGHT late (δ>0). Each hit is a vertical tick
        at X = (δ/maxHitWindow + 1) / 2 (getRelativeJudgementPosition, rotated).
        Fade in 100ms @ 0.6 then fade out 5000ms (JudgementLine.PrepareForUse).
        """
        if not self.replay:
            return
        from .hud import mania_hit_windows, result_for_offset

        draw = ImageDraw.Draw(frame, "RGBA")
        # Strict JSON placement: x,y = anchor + Position (passed from _place).
        # Origin=CentreLeft + Rotation=−90 → origin at left end, mid-thickness of horizontal bar.
        scale = float(item.scale_x) if item.scale_x and item.scale_x > 0 else 1.6
        bar_len = int(200 * scale)
        bar_h = max(8, int(14 * scale))
        chevron = max(6, int(8 * scale))
        # place at screen bottom-centre (中下) — always, ignore JSON pos
        cx = VIEW_W * 0.5
        cy = VIEW_H - 20.0
        x0 = cx - bar_len / 2
        y0 = cy - bar_h / 2

        win = mania_hit_windows(self.bm.od or 8.0)
        max_win = max(1.0, win["meh"])
        thickness = max(2, int(3 * scale / 1.5))

        def rel_x(offset_ms: float) -> float:
            # same formula as getRelativeJudgementPosition, then applied on X (rot −90)
            t = (offset_ms / max_win + 1.0) / 2.0
            return min(1.0, max(0.0, t))

        colors = {
            "perfect": (245, 215, 110, 200),
            "great": (110, 193, 228, 200),
            "good": (143, 214, 148, 200),
            "ok": (240, 168, 104, 200),
            "meh": (224, 108, 117, 200),
        }

        # colour axis: early=left, late=right (after rot −90)
        for name in ("meh", "ok", "good", "great", "perfect"):
            frac = win[name] / max_win
            half = (bar_len / 2) * frac
            col = colors[name]
            draw.rectangle([cx - half, cy - 2, cx, cy + 1], fill=col)  # early side
            draw.rectangle([cx, cy - 1, cx + half, cy + 2], fill=col)  # late side

        # centre marker
        draw.rectangle([cx - 2, cy - 4, cx + 2, cy + 4], fill=(255, 255, 255, 220))

        now = now_ms
        for t_off, delta in self.events.hit_events:
            age = now - t_off
            if age < 0 or age > 5100:
                continue
            if age < 100:
                alpha = 0.6 * (age / 100.0)
                height_frac = age / 100.0
            else:
                alpha = 0.6 * (1.0 - (age - 100) / 5000.0)
                height_frac = 1.0 - 0.5 * ((age - 100) / 5000.0)
            if alpha <= 0.01:
                continue
            rx = rel_x(float(delta))
            xx = x0 + rx * bar_len
            col = colors.get(result_for_offset(float(delta), win), (255, 255, 255, 255))
            a = int(255 * min(1.0, alpha / 0.6) * 0.85)
            half_h = (bar_h / 2 + chevron * 0.35) * height_frac
            # vertical tick at this δ
            draw.line([xx, cy - half_h, xx, cy + half_h], fill=(col[0], col[1], col[2], a), width=thickness)

        # moving-average chevron (EMA 0.9/0.1) — points along error axis
        if self.events.hit_events:
            avg = 0.0
            for _t, d in self.events.hit_events:
                if _t > now:
                    break
                avg = avg * 0.9 + d * 0.1
            ax = x0 + rel_x(avg) * bar_len
            s = chevron * 0.45
            draw.polygon([(ax - s, cy - s), (ax - s, cy + s), (ax, cy)], fill=(255, 255, 255, 200))

    def _is_playfield_idle(self, now_ms: float) -> bool:
        """True when no notes/LNs/lights can touch the scroll band."""
        from bisect import bisect_left, bisect_right

        span = self.geom.time_range * 3
        if bisect_right(self._obj_starts, now_ms + span) > bisect_left(self._obj_starts, now_ms - span):
            return False
        lo = bisect_left(self._hold_starts, now_ms - span)
        for a, b, _c in self._holds_sorted[lo : lo + 16]:
            if a > now_ms + span:
                break
            if b >= now_ms - span:
                return False
        if bisect_right(self._press_times, now_ms) > bisect_left(self._press_times, now_ms - 200):
            return False
        return True

    def render_frame(self, now_ms: float) -> Image.Image:
        st = hud_state_at(self.events, self.bm, now_ms, self._length_s)

        # dirty-rect: static frame cached as raw bytes — frombytes is a single memcpy
        if getattr(self, "_static_bytes", None) is None:
            self._static_stage()  # ensure _static_cache is built
            self._static_bytes = self._static_cache.tobytes()
        frame = Image.frombytes("RGBA", VIEW, self._static_bytes)
        self._compose_stage(frame, now_ms)
        if self.replay:
            # CentreLeft (JSON int 10) — left-middle of screen
            _ax, ay = _anchor_xy(10)
            self._draw_replay_judgement_panel(frame, 28.0, ay, now_ms)

        # HUD
        if self.skin.layout:
            roles = self.skin.layout
            for item in roles:
                from .skin import classify_type

                cls = classify_type(item.type_name)
                if not cls or cls[0] == "__skip__":
                    continue
                role = cls[0]
                if role == ROLE_BAR_ERROR and not self.replay:
                    continue
                self._place(frame, item, st, now_ms, fallback_role=role)
        else:
            for role, (ax, dx, dy) in DEFAULT_LAYOUT.items():
                if role == ROLE_BAR_ERROR and not self.replay:
                    continue
                dummy = SerialisedDrawable(type_name=role, anchor=ax, origin=ax, x=dx, y=dy)
                self._place(frame, dummy, st, now_ms, fallback_role=role)

        return frame

    def render_mp4(
        self,
        out_path: Path,
        start_s: float,
        end_s: float,
        lead_in_s: float = 0.0,
        progress_cb=None,
        scale_to: tuple[int, int] | None = None,
    ) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # lead-in: when the clip starts at song t=0, run the clock 1s early so
        # notes scroll in instead of appearing already on the judgement line
        lead = max(0.0, float(lead_in_s))
        if start_s <= 1e-6 and lead <= 0.0:
            lead = 1.0
        t_start = start_s - lead
        span_s = (end_s - start_s) + lead
        self._length_s = max(0.001, end_s - start_s)

        t0 = t_start * 1000.0
        t1 = end_s * 1000.0
        n = int(round(span_s * self.fps)) + 1

        ffmpeg = _find_ffmpeg()
        audio_in = self.audio_path
        tmpdir = Path(tempfile.mkdtemp(prefix="mr_audio_"))
        try:
            # stream raw frames to ffmpeg (no per-frame PNG on disk)
            if lead > 0:
                acmd = [
                    ffmpeg, "-y",
                    "-f", "lavfi", "-t", f"{lead:.6f}",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-ss", str(start_s),
                    "-t", str(max(0.01, end_s - start_s + (1.0 / self.fps))),
                    "-i", str(audio_in),
                    "-filter_complex", "[0:a:0][1:a:0]concat=n=2:v=0:a=1[a]",
                    "-map", "[a]", "-c:a", "aac",
                    str(tmpdir / "audio_padded.m4a"),
                ]
                proc = subprocess.run(acmd, capture_output=True)
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-2000:])
                audio_args = ["-i", str(tmpdir / "audio_padded.m4a")]
            else:
                audio_args = [
                    "-ss", str(start_s),
                    "-t", str(max(0.01, end_s - start_s + (1.0 / self.fps))),
                    "-i", str(audio_in),
                ]

            cmd = [
                ffmpeg, "-y",
                "-f", "rawvideo",
                "-pix_fmt", "rgb24",
                "-s", f"{VIEW_W}x{VIEW_H}",
                "-r", str(self.fps),
                "-i", "-",
                *audio_args,
                "-map", "0:v:0", "-map", "1:a:0",
                # The renderer's geometry is fixed at 1920x1080, so any other output size is
                # a scale here — which also makes 720p a clean supersample, rather than a
                # second layout of every lane width and judgement position.
                *(["-vf", f"scale={scale_to[0]}:{scale_to[1]}:flags=bicubic"] if scale_to else []),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-threads", "0",
                "-pix_fmt", "yuv420p",
                "-r", str(self.fps),
                "-shortest",
                "-f", "mp4",
                "-movflags", "+faststart",
                str(out_path),
            ]
            # stderr must NOT be a pipe we only drain at the end — ffmpeg fills it and deadlocks
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=open(tmpdir / "ffmpeg.log", "wb"),
            )
            assert proc.stdin is not None
            workers = max(2, min(16, (os.cpu_count() or 4) - 2))
            try:
                last_bytes: bytes | None = None
                last_hud_key = None
                n_reused = 0

                def _encode_one(i: int) -> tuple[int, bytes, tuple, bool]:
                    now = t0 + (t1 - t0) * (i / max(1, n - 1))
                    return _render_frame_task((i, now))

                t_render_start = time.monotonic()
                in_flight = workers * 2
                q: deque = deque()
                # ProcessPoolExecutor: true parallelism (bypass GIL). Falls back to
                # threads if the caller lacks __main__ guard (Windows spawn).
                pool_cls = ProcessPoolExecutor
                pool_kwargs = {"initializer": _init_render_worker, "initargs": (self,)}
                try:
                    with pool_cls(max_workers=workers, **pool_kwargs) as ex:
                        for i in range(n):
                            now = t0 + (t1 - t0) * (i / max(1, n - 1))
                            q.append(ex.submit(_render_frame_task, (i, now)))
                            if len(q) >= in_flight:
                                fut = q.popleft()
                                _i, raw, hud_key, idle = fut.result()
                                if last_bytes is not None and last_hud_key == hud_key and idle:
                                    proc.stdin.write(last_bytes)
                                    n_reused += 1
                                else:
                                    proc.stdin.write(raw)
                                    last_bytes, last_hud_key = raw, hud_key
                                if progress_cb and (_i % 15 == 0 or _i == n - 1):
                                    progress_cb(_i, n, n_reused)
                        while q:
                            _i, raw, hud_key, idle = q.popleft().result()
                            if last_bytes is not None and last_hud_key == hud_key and idle:
                                proc.stdin.write(last_bytes)
                                n_reused += 1
                            else:
                                proc.stdin.write(raw)
                                last_bytes, last_hud_key = raw, hud_key
                            if progress_cb and (_i % 15 == 0 or _i == n - 1):
                                progress_cb(_i, n, n_reused)
                except (RuntimeError, OSError):
                    # spawn guard missing / IPC failure → thread fallback
                    print("[perf] ProcessPool unavailable, falling back to threads", file=sys.stderr)
                    q.clear()
                    with ThreadPoolExecutor(max_workers=workers) as ex:
                        for i in range(n):
                            now = t0 + (t1 - t0) * (i / max(1, n - 1))
                            q.append(ex.submit(_render_frame_task, (i, now)))
                            if len(q) >= in_flight:
                                fut = q.popleft()
                                _i, raw, hud_key, idle = fut.result()
                                if last_bytes is not None and last_hud_key == hud_key and idle:
                                    proc.stdin.write(last_bytes)
                                    n_reused += 1
                                else:
                                    proc.stdin.write(raw)
                                    last_bytes, last_hud_key = raw, hud_key
                                if progress_cb and (_i % 15 == 0 or _i == n - 1):
                                    progress_cb(_i, n, n_reused)
                        while q:
                            _i, raw, hud_key, idle = q.popleft().result()
                            if last_bytes is not None and last_hud_key == hud_key and idle:
                                proc.stdin.write(last_bytes)
                                n_reused += 1
                            else:
                                proc.stdin.write(raw)
                                last_bytes, last_hud_key = raw, hud_key
                            if progress_cb and (_i % 15 == 0 or _i == n - 1):
                                progress_cb(_i, n, n_reused)
                t_render_end = time.monotonic()
                n_reused_str = f", reused {n_reused}/{n}" if n_reused else ""
                print(
                    f"[perf] render {n} frames in {t_render_end - t_render_start:.1f}s "
                    f"({n / max(0.01, t_render_end - t_render_start):.1f} fps) "
                    f"workers={workers}{n_reused_str}",
                    file=sys.stderr,
                    flush=True,
                )
            finally:
                proc.stdin.close()
                rc = proc.wait()
                if rc != 0:
                    log = (tmpdir / "ffmpeg.log")
                    tail = log.read_bytes()[-2000:].decode("utf-8", "replace") if log.exists() else ""
                    raise RuntimeError(f"ffmpeg rc={rc} {tail}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        return out_path
