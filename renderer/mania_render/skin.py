from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .models import ManiaSkinBlock, SerialisedDrawable

# type-name suffix -> role
ROLE_COMBO = "combocounter"
ROLE_CPS = "clickspersecondcounter"
ROLE_SONG_PROGRESS = "songprogress"
ROLE_ATTRIBUTE = "beatmapattributetext"
ROLE_BPM = "bpmcounter"
ROLE_ACCURACY = "accuracycounter"
ROLE_BAR_ERROR = "barhiterrormeter"

REQUIRED_ROLES = (
    ROLE_COMBO,
    ROLE_CPS,
    ROLE_SONG_PROGRESS,
    ROLE_ATTRIBUTE,
    ROLE_BPM,
    ROLE_ACCURACY,
)

# concrete class name (suffix) -> role / priority (lower wins)
_TYPE_ROLE = {
    "legacymaniacombocounter": (ROLE_COMBO, 0),
    "legacydefaultcombocounter": (ROLE_COMBO, 1),
    "argonmaniacombocounter": (ROLE_COMBO, 1),
    "argoncombocounter": (ROLE_COMBO, 2),
    "defaultcombocounter": (ROLE_COMBO, 3),
    "combocounter": (ROLE_COMBO, 4),
    "clickspersecondcounter": (ROLE_CPS, 0),
    "legacysongprogress": (ROLE_SONG_PROGRESS, 0),
    "defaultsongprogress": (ROLE_SONG_PROGRESS, 1),
    "argonsongprogress": (ROLE_SONG_PROGRESS, 2),
    "songprogress": (ROLE_SONG_PROGRESS, 3),
    "beatmapattributetext": (ROLE_ATTRIBUTE, 0),
    "bpmcounter": (ROLE_BPM, 0),
    "legacyaccuracycounter": (ROLE_ACCURACY, 0),
    "defaultaccuracycounter": (ROLE_ACCURACY, 1),
    "argonaccuracycounter": (ROLE_ACCURACY, 2),
    "accuracycounter": (ROLE_ACCURACY, 3),
    "barhiterrormeter": (ROLE_BAR_ERROR, 0),
}

# never render
_SKIP_SUFFIX = (
    "spectatorlist",
    "playeravatar",
    "playerteamflag",
    "drawablegameplayleaderboard",
    "gameplayleaderboard",
    "playername",
    "playerflag",
)

# default layout when no JSON (CONTEXT.md)
DEFAULT_LAYOUT = {
    ROLE_COMBO: (9, 20.0, 20.0),            # TopLeft
    ROLE_ATTRIBUTE: (33, -20.0, 20.0),       # TopRight
    ROLE_BPM: (33, -20.0, 55.0),            # TopRight
    ROLE_SONG_PROGRESS: (33, -20.0, 100.0),  # TopRight
    ROLE_ACCURACY: (36, -20.0, -50.0),      # BottomRight
    ROLE_CPS: (36, -20.0, -90.0),           # BottomRight
    ROLE_BAR_ERROR: (20, 0.0, -240.0),      # BottomCentre, ~240px up (JSON-style)
}


def _type_suffix(full: str) -> str:
    name = full.split(",")[0].strip()
    return name.rsplit(".", 1)[-1].lower()


def classify_type(full: str) -> tuple[str | None, int] | None:
    s = _type_suffix(full)
    if s in _SKIP_SUFFIX:
        return ("__skip__", 99)
    if s in _TYPE_ROLE:
        return _TYPE_ROLE[s]
    # inheritance-style contains match
    if "barhiterrormeter" in s:
        return (ROLE_BAR_ERROR, 1)
    if "hiterrormeter" in s:
        return ("__skip__", 99)
    if "combocounter" in s:
        return (ROLE_COMBO, 5)
    if "clickspersecond" in s:
        return (ROLE_CPS, 1)
    if "songprogress" in s:
        return (ROLE_SONG_PROGRESS, 4)
    if "beatmapattribute" in s:
        return (ROLE_ATTRIBUTE, 1)
    if "bpmcounter" in s or s == "bpm":
        return (ROLE_BPM, 1)
    if "accuracycounter" in s or ("accuracy" in s and "counter" in s):
        return (ROLE_ACCURACY, 4)
    return None


@dataclass
class SkinTextures:
    """Loaded images keyed by basename without extension (lowercase)."""

    images: dict[str, Image.Image] = field(default_factory=dict)

    def get(self, name: str | None) -> Image.Image | None:
        if not name:
            return None
        raw = name.replace("\\", "/")
        stem = Path(raw).stem.lower()
        # exact stem first, then stem0 / stem1 (Orbs\BLUE → blue → blue1)
        for key in (stem, f"{stem}0", f"{stem}1"):
            img = self.images.get(key)
            if img is not None:
                return img
        return None


@dataclass
class LoadedSkin:
    name: str = ""
    root_block: ManiaSkinBlock | None = None
    blocks: dict[int, ManiaSkinBlock] = field(default_factory=dict)
    layout: list[SerialisedDrawable] = field(default_factory=list)
    textures: SkinTextures = field(default_factory=SkinTextures)
    has_layout_json: bool = False

    def block_for_keys(self, keys: int) -> ManiaSkinBlock | None:
        if keys in self.blocks:
            return self.blocks[keys]
        return self.root_block


def _strip_ini_comment(line: str) -> str:
    # skin.ini often has "key: value // comment" (CJK comments included)
    if "//" in line:
        line = line.split("//", 1)[0]
    return line.strip()


def _parse_ini_mania(text: str) -> dict[int, ManiaSkinBlock]:
    blocks: dict[int, ManiaSkinBlock] = {}
    current: ManiaSkinBlock | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if line.lower() == "[mania]":
            current = ManiaSkinBlock()
            continue
        if line.startswith("["):
            current = None
            continue
        if current is None or ":" not in line:
            continue
        line = _strip_ini_comment(line)
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        kl = k.lower()
        if kl == "keys":
            try:
                current.keys = int(v)
            except ValueError:
                pass
            blocks[current.keys] = current
        elif kl == "columnstart":
            current.column_start = float(v)
        elif kl == "columnwidth":
            # parseArrayValue: ColumnWidth applies STABLE_MAGIC_SCALE_FACTOR 1.6
            current.column_width = [float(x) * 1.6 for x in v.split(",") if x.strip()]
        elif kl == "columnlinewidth":
            # parseArrayValue(..., applyScaleFactor=False)
            current.column_line_width = [float(x) for x in v.split(",") if x.strip()]
        elif kl == "columnspacing":
            pass
        elif kl == "hitposition":
            # skin.ini HitPosition = Y from TOP in 480-space (stable).
            # Store as view-ready: y_view = value / 480 * 1080
            try:
                y480 = float(v)
            except ValueError:
                y480 = 402.0
            y480 = min(480.0, max(240.0, y480))
            current.hit_position = y480 / 480.0 * 1080.0  # view Y from top
        elif kl == "comboseparator" or kl == "combowidth":
            pass
        elif kl == "comboseparator":
            pass
        elif kl == "comboposition":
            current.combo_position = float(v) * 1.6
        elif kl == "lightposition":
            current.light_position = float(v) * 1.6
        elif kl == "upsidedown":
            current.upside_down = v.strip() in ("1", "true")
        elif kl == "keysundernotes":
            current.keys_under_notes = v.strip() in ("1", "true")
        elif kl == "judgementline":
            current.judgement_line = v.strip() in ("1", "true")
        elif kl == "stagehint":
            current.stage_hint = v.strip()
        elif kl == "widthfornoteheightscale":
            try:
                current.width_for_note_height = float(v) * 1.6
            except ValueError:
                pass
        elif kl == "lightingnwidth":
            current.explosion_width = [float(x) * 1.6 for x in v.split(",") if x.strip()]
        elif kl == "lightinglwidth":
            current.hold_light_width = [float(x) * 1.6 for x in v.split(",") if x.strip()]
        elif kl.startswith("noteimage"):
            # NoteImage{n}, NoteImage{n}H/L/T
            rest = k[len("NoteImage") :]
            col_s = rest[:1] if not rest[:2].isdigit() else rest[:2]
            suffix = rest[len(col_s) :].upper() if col_s.isdigit() else ""
            # keys are NoteImage0.. so single digit typical
            digits = ""
            i = 0
            while i < len(rest) and rest[i].isdigit():
                digits += rest[i]
                i += 1
            suffix = rest[i:].upper()
            if not digits:
                continue
            col = int(digits)
            slot = {"": "body", "H": "head", "L": "hold", "T": "tail"}.get(suffix)
            if not slot:
                continue
            current.note_images.setdefault(col, {})[slot] = v.strip()
        elif kl.startswith("keyimage"):
            # KeyImage{n} / KeyImage{n}D → up/down
            rest = k[len("KeyImage") :]
            digits = ""
            i = 0
            while i < len(rest) and rest[i].isdigit():
                digits += rest[i]
                i += 1
            suffix = rest[i:].upper()
            if not digits:
                continue
            col = int(digits)
            slot = "down" if suffix == "D" else "up"
            current.key_images.setdefault(col, {})[slot] = v.strip()
        elif kl == "lightingn":
            current.lighting_n = v.strip()
        elif kl == "lightingl":
            current.lighting_l = v.strip()
    return blocks


def _parse_layout_json(raw: bytes) -> list[SerialisedDrawable]:
    text = raw.decode("utf-8", "replace")
    data = json.loads(text)
    items: list[dict]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        di = data.get("DrawableInfo") or {}
        items = list(di.get("global") or []) + list(di.get("mania") or [])
    else:
        return []

    def conv(d: dict) -> SerialisedDrawable:
        pos = d.get("Position") or {}
        scale = d.get("Scale") or {}
        children = [conv(c) for c in (d.get("Children") or [])]
        return SerialisedDrawable(
            type_name=str(d.get("Type") or ""),
            anchor=int(d.get("Anchor") or 9),
            origin=int(d.get("Origin") or 9),
            x=float(pos.get("x") or 0),
            y=float(pos.get("y") or 0),
            scale_x=float(scale.get("x") or 1),
            scale_y=float(scale.get("y") or 1),
            rotation=float(d.get("Rotation") or 0),
            width=d.get("Width"),
            height=d.get("Height"),
            uses_fixed_anchor=bool(d.get("UsesFixedAnchor")),
            settings=dict(d.get("Settings") or {}),
            children=children,
        )

    return [conv(d) for d in items]


def pick_roles(layout: list[SerialisedDrawable], allow_bar_error: bool) -> dict[str, SerialisedDrawable]:
    """Resolve Required HUD (+ optional bar meter) with Legacy→Default→first priority."""
    best: dict[str, tuple[int, int, SerialisedDrawable]] = {}
    for idx, item in enumerate(layout):
        cls = classify_type(item.type_name)
        if not cls:
            continue
        role, prio = cls
        if role == "__skip__":
            continue
        if role == ROLE_BAR_ERROR and not allow_bar_error:
            continue
        cur = best.get(role)
        if cur is None or (prio, idx) < (cur[0], cur[1]):
            best[role] = (prio, idx, item)
    return {role: item for role, (_, _, item) in best.items()}


def load_skin(path: str | Path) -> LoadedSkin:
    path = Path(path)
    skin = LoadedSkin(name=path.stem)
    # osk is zip; unpacked folder also allowed
    if path.is_dir():
        files = {}
        for p in path.rglob("*"):
            if not p.is_file():
                continue
            key = p.name.lower()
            # root-level wins over extras/variants
            rel = p.relative_to(path).as_posix().lower()
            score = (rel.count("/"), rel.startswith("!"), len(rel))
            if key not in files or score < files[key][0]:
                files[key] = (score, p)
        read = lambda n: files[n.lower()][1].read_bytes() if n.lower() in files else None  # noqa: E731
        names = [info[1].name for info in files.values()]
    else:
        zf = zipfile.ZipFile(path, "r")
        # prefer root-level entries over !Extras colour packs (same basename)
        best: dict[str, tuple[tuple, str]] = {}
        for n in zf.namelist():
            if n.endswith("/"):
                continue
            key = Path(n).name.lower()
            rel = n.replace("\\", "/").lower()
            score = (rel.count("/"), rel.startswith("!"), len(rel))
            if key not in best or score < best[key][0]:
                best[key] = (score, n)
        index = {k: v[1] for k, v in best.items()}
        names = [Path(v).name for v in index.values()]
        read = lambda n: zf.read(index[n.lower()]) if n.lower() in index else None  # noqa: E731

    ini = read("skin.ini")
    if ini:
        blocks = _parse_ini_mania(ini.decode("utf-8", "replace"))
        skin.blocks = blocks
        # prefer 4 as root display block
        skin.root_block = blocks.get(4) or next(iter(blocks.values()), None)

    for fname in ("MainHUDComponents.json", "Playfield.json"):
        raw = read(fname)
        if raw:
            skin.layout.extend(_parse_layout_json(raw))
            skin.has_layout_json = True

    # load png/jpg textures. Root-level files win; never let !Extras override (osu loads the skin root).
    # skip huge ranking panels
    for name in sorted(names, key=lambda s: (s.count("/") + s.count("!"), len(s))):
        low = name.lower()
        if not low.endswith((".png", ".jpg", ".jpeg")):
            continue
        stem = Path(name).stem.lower()
        if "ranking" in stem or "selection" in stem:
            continue
        if stem in skin.textures.images:
            continue  # already have a higher-priority copy
        # skip extras colour packs
        raw_name = name
        if raw_name.startswith("!") or "/!" in raw_name or "extras" in raw_name:
            # still allow if nothing else provides this stem later — load last
            pass
        raw = read(Path(name).name)
        if not raw:
            continue
        try:
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            continue
        # osu! draws `@2x` sprites at HALF their pixel size — the skin loader sets
        # ScaleAdjust = 2 for them (osu.Framework `Texture` / osu! stable's
        # `SkinConfiguration`). Halving once, right here, fixes every consumer at
        # once; aspect ratios are untouched, so lane/note geometry is unaffected.
        # Without this the texture is drawn at double size: boj's `Receptor@2x`
        # (150x375) came out 527px tall instead of 264 — a visible 2x vertical
        # stretch on the receptors, and the same doubles any other @2x sprite.
        if stem.endswith("@2x"):
            img = img.resize(
                (max(1, round(img.width / 2)), max(1, round(img.height / 2))),
                Image.Resampling.LANCZOS,
            )
        skin.textures.images[stem] = img

    return skin
