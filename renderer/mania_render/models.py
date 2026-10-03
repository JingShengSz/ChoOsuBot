from __future__ import annotations

from dataclasses import dataclass, field


# Anchor ints empirically used in lazer Layout JSON (see CONTEXT.md).
# Verified against Cho' Skin MainHUDComponents.json:
#   BarHitErrorMeter Anchor=20 Origin=10  → BottomCentre + CentreLeft
#   SongProgress Anchor=20 → BottomCentre; Combo Anchor=12 → BottomLeft
#   LegacySongProgress Anchor=33 → TopRight; BPM/CPS Anchor=36 → BottomRight
ANCHOR_POINT = {
    9: (0.0, 0.0),    # TopLeft
    17: (0.5, 0.0),   # TopCentre
    33: (1.0, 0.0),   # TopRight
    10: (0.0, 0.5),   # CentreLeft
    18: (0.5, 0.5),   # Centre
    34: (1.0, 0.5),   # CentreRight
    12: (0.0, 1.0),   # BottomLeft
    20: (0.5, 1.0),   # BottomCentre
    36: (1.0, 1.0),   # BottomRight
}
ANCHOR_NAME = {
    9: "TopLeft",
    17: "TopCentre",
    33: "TopRight",
    10: "CentreLeft",
    18: "Centre",
    34: "CentreRight",
    12: "BottomLeft",
    20: "BottomCentre",
    36: "BottomRight",
}

HIT_CIRCLE = 1
HIT_SLIDER = 2
HIT_SPINNER = 8
HIT_LONGNOTE = 128


@dataclass
class TimingPoint:
    time: int
    beat_length: float
    is_red_line: bool

    @property
    def bpm(self) -> float:
        return 60000.0 / self.beat_length if self.beat_length > 0 else 0.0


@dataclass
class HitObject:
    flags: int
    start_time: int
    end_time: int
    column: int
    is_hold: bool
    x: int = 0


@dataclass
class OsuBeatmap:
    title: str = ""
    artist: str = ""
    creator: str = ""
    version: str = ""
    tags: str = ""
    audio_filename: str = "audio.mp3"
    background_filename: str = ""
    beatmap_id: str = ""
    beatmapset_id: str = ""
    mode: int = 3
    cs: float = 4.0
    od: float = 5.0
    hp: float = 5.0
    ar: float = 5.0
    timings: list[TimingPoint] = field(default_factory=list)
    hit_objects: list[HitObject] = field(default_factory=list)

    @property
    def keys(self) -> int:
        return max(1, int(round(self.cs)))

    @property
    def red_bpms(self) -> list[float]:
        return [t.bpm for t in self.timings if t.is_red_line and t.beat_length > 0]

    @property
    def duration_s(self) -> float:
        if not self.hit_objects:
            return 0.0
        end = max(h.end_time for h in self.hit_objects)
        start = min(h.start_time for h in self.hit_objects)
        return (end - start) / 1000.0 + 0.5

    @property
    def end_time_ms(self) -> int:
        return max((h.end_time for h in self.hit_objects), default=0)

    def apply_mirror(self) -> None:
        """Apply ManiaModMirror: `Column = (columnCount - 1) - Column` per hit object.

        `Mirror` is a play-time transform — the .osu file is untouched, the client
        mirrors the notes as it loads them — so a replay played with it records key
        presses in mirrored space. Applying the same flip to the hit objects puts the
        picture and the judgements back on the chart the player actually saw.
        """
        keys = self.keys
        for h in self.hit_objects:
            h.column = (keys - 1) - h.column


@dataclass
class ManiaSkinBlock:
    keys: int = 4
    column_start: float = 0.0
    column_width: list[float] = field(default_factory=list)
    column_line_width: list[float] = field(default_factory=list)
    hit_position: float = 675.0  # view Y from top; from skin.ini HitPosition/480*1080
    combo_position: float = 177.6  # from top, 768-scale
    light_position: float = 643.2
    upside_down: bool = False
    keys_under_notes: bool = True
    # LegacyManiaSkinConfiguration.ShowJudgementLine defaults to TRUE; a skin turns the
    # 1px bar off with `JudgementLine: 0`.
    judgement_line: bool = True
    # `StageHint` override; empty means the `mania-stage-hint` default. The sprite is
    # drawn even when `JudgementLine` is off (LegacyHitTarget always adds it) — a skin
    # can therefore ship an invisible hint (`StageHint: blank`) and no line at all.
    stage_hint: str = ""
    note_images: dict[int, dict[str, str]] = field(default_factory=dict)
    # col -> {up, down} from KeyImage{n} / KeyImage{n}D
    key_images: dict[int, dict[str, str]] = field(default_factory=dict)
    lighting_n: str = ""  # LightingN override
    lighting_l: str = ""  # LightingL override
    explosion_width: list[float] = field(default_factory=list)  # LightingNWidth
    hold_light_width: list[float] = field(default_factory=list)  # LightingLWidth
    # col -> {body, head, tail, hold} filenames without extension
    width_for_note_height: float | None = None


@dataclass
class SerialisedDrawable:
    type_name: str
    anchor: int = 9
    origin: int = 9
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    width: float | None = None
    height: float | None = None
    uses_fixed_anchor: bool = False
    settings: dict = field(default_factory=dict)
    children: list[SerialisedDrawable] = field(default_factory=list)


@dataclass
class ReplayPress:
    time_ms: int
    column: int


@dataclass
class ReplayData:
    presses: list[ReplayPress] = field(default_factory=list)
    releases: list[ReplayPress] = field(default_factory=list)
    #: True for a legacy (osu!stable) replay.  LegacyScoreDecoder appends
    #: ModClassic to every score whose version is below FIRST_LAZER_VERSION, and
    #: the Classic mod switches ManiaHitWindows to the classic window set — see
    #: mania_render/judge.py.  Getting this wrong changes the windows on low-OD
    #: maps by more than 10 ms.
    classic: bool = False
    #: The judgement counts osu! itself recorded for this play (the .osr header).
    #: They are the authoritative tally: the renderer pins its own counter to
    #: them so the displayed accuracy is the game's, not an approximation of it
    #: (see judge.reconcile), and their total is what selects the object model
    #: (a stable replay counts a hold once, a lazer replay twice).
    counts: dict[str, int] | None = None


@dataclass
class FrameEvents:
    """Per-frame synthetic events for HUD (FC Sim or replay-derived)."""

    clicks: list[int] = field(default_factory=list)  # ms
    combo_samples: list[tuple[int, int]] = field(default_factory=list)  # (ms, combo)
    hit_offsets: list[float] = field(default_factory=list)  # ms, for bar meter
    # (time_ms, offset_ms) per judged hit — BarHitErrorMeter samples
    hit_events: list[tuple[int, float]] = field(default_factory=list)
    # (object_start_ms, offset_ms) 1:1 with objects matched to a press
    hit_pairs: list[tuple[int, float]] = field(default_factory=list)
    key_held: dict[int, list[tuple[int, int]]] = field(default_factory=dict)  # col -> (start,end) ms
    # Every accuracy-affecting judgement, as mania_render.judge produces them
    # (head AND tail, with the time lazer would apply each one).  The ACC counter
    # reads this: counting `hit_pairs` instead is what made a hold note one
    # judgement instead of two, and a PERFECT worth 300 instead of 305.
    judgements: list = field(default_factory=list)
