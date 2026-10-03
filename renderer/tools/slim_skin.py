"""Repack a skin with only the files the mania renderer can actually reference.

Why this exists: whoever renders has to download the archive, unzip it and decode every
image in it. Measured on the registered skins, **0.1 % - 24 %** of the bytes are ever
referenced — Suisei is 181 MB of which the mania renderer needs ~0.1 MB, and that
difference shows up directly as RAM in both render paths (the browser holds the whole zip
plus every decoded bitmap; the Python loader decodes every PNG into RGBA).

Pure zip I/O: no image is decoded, so this is cheap enough to run on a 2-core box.

    python tools/slim_skin.py "<in.osk>" "<out.osk>" [--keys 4]

Only `[Mania]` blocks for the requested key counts are kept; pass `--keys` repeatedly or
omit it to keep every block.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import zipfile

# Everything `mania-web` or `mania_render` can look up by hard-coded name.
CORE_PREFIXES = (
    "mania-note", "mania-key", "mania-stage-", "mania-stage-light", "mania-stage-hint",
    "mania-hit", "mania-warningarrow", "lighting", "comboburst",
)
# The page's own assets, and the HUD layout the Python renderer reads.
ALWAYS_EXACT = {"skin.ini", "mainhudcomponents.json", "playfield.json"}
# skin.ini keys whose value is a sprite path we must keep.
INI_PATH_KEYS = {
    "lightingn", "lightingl", "stagelight", "stagehint", "leftstageimage",
    "rightstageimage", "bottomstageimage", "warningarrow", "hit300g", "hit300",
    "hit200", "hit100", "hit50", "hit0",
}


def strip_frame_suffix(stem: str) -> str:
    """`mania-note1L-12@2x` -> `mania-note1L` so a prefix test matches every frame."""
    s = re.sub(r"@2x$", "", stem, flags=re.I)
    return re.sub(r"-\d+$", "", s)


def wanted_names(names: list[str]) -> tuple[set[str], set[str]]:
    """Collect exact sprite paths and bare stems mentioned by skin.ini."""
    exact: set[str] = set()
    stems: set[str] = set()
    for n in names:
        if pathlib.PurePosixPath(n).name.lower() != "skin.ini":
            continue
        continue
    return exact, stems


def slim(src: pathlib.Path, dst: pathlib.Path, keys: set[int] | None) -> dict:
    with zipfile.ZipFile(src) as zin:
        entries = [e for e in zin.infolist() if not e.is_dir()]
        by_name = {e.filename.replace("\\", "/").lower(): e for e in entries}

        # ── skin.ini: read it, optionally drop [Mania] blocks we do not need ──
        ini_entry = next((e for k, e in by_name.items() if pathlib.PurePosixPath(k).name == "skin.ini"), None)
        ini_text = zin.read(ini_entry).decode("utf-8", "replace") if ini_entry else None

        extra_paths: set[str] = set()
        if ini_text:
            for line in ini_text.splitlines():
                line = line.split("//")[0].strip()
                if ":" not in line:
                    continue
                k, _, v = line.partition(":")
                k = k.strip().lower()
                v = v.strip()
                if not v:
                    continue
                if k.startswith(("noteimage", "keyimage")) or k in INI_PATH_KEYS:
                    p = v.replace("\\", "/").lower()
                    extra_paths.add(p)
                    if not p.endswith(".png") and not p.endswith(".jpg"):
                        extra_paths.add(p + ".png")
                    extra_paths.add(pathlib.PurePosixPath(p).stem)

        keep: list[zipfile.ZipInfo] = []
        for e in entries:
            low = e.filename.replace("\\", "/").lower()
            base = pathlib.PurePosixPath(low).name
            stem = pathlib.PurePosixPath(low).stem
            core = strip_frame_suffix(stem)
            if base in ALWAYS_EXACT:
                keep.append(e)
                continue
            if any(core.startswith(p) for p in CORE_PREFIXES):
                keep.append(e)
                continue
            if low in extra_paths or core in extra_paths or stem in extra_paths:
                keep.append(e)

        dst.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for e in keep:
                data = zin.read(e)
                if e.filename.replace("\\", "/").lower().endswith("skin.ini") and keys and ini_text:
                    data = filter_ini(ini_text, keys).encode("utf-8")
                zout.writestr(e.filename, data)

    total = sum(e.file_size for e in entries)
    kept = sum(e.file_size for e in keep)
    return {"files": len(entries), "kept": len(keep), "whole_mb": total / 1048576, "kept_mb": kept / 1048576}


def filter_ini(text: str, keys: set[int]) -> str:
    """Keep [General]/[Colours]/[Fonts] and only the [Mania] blocks we asked for."""
    out: list[str] = []
    emit = True
    current_keys: int | None = None
    block: list[str] = []

    def flush() -> None:
        if current_keys is None or current_keys in keys:
            out.extend(block)

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            if current_keys is not None:
                flush()
                block = []
                current_keys = None
            emit = section != "mania"
            if section == "mania":
                current_keys = -1          # unknown until Keys: is seen
            out.append(line)
            continue
        if current_keys is not None:
            block.append(line)
            m = re.match(r"\s*keys\s*:\s*(\d+)", line, re.I)
            if m:
                current_keys = int(m.group(1))
            continue
        if emit:
            out.append(line)
    if current_keys is not None:
        flush()
    # rebuild: the flush() above appended blocks after their section headers, so just
    # re-derive by walking again (simpler and correct):
    return _filter_ini_simple(text, keys)


def _filter_ini_simple(text: str, keys: set[int]) -> str:
    head: list[str] = []
    blocks: list[tuple[int | None, list[str]]] = []
    cur_header: list[str] = []
    cur_body: list[str] = []
    cur_keys: int | None = None
    section = ""

    def close() -> None:
        if not cur_header and not cur_body:
            return
        if section == "mania":
            blocks.append((cur_keys, cur_header + cur_body))
        else:
            head.extend(cur_header + cur_body)

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            close()
            section = s[1:-1].strip().lower()
            cur_header, cur_body, cur_keys = [line], [], None
            continue
        if section == "mania":
            cur_body.append(line)
            m = re.match(r"\s*keys\s*:\s*(\d+)", line, re.I)
            if m:
                cur_keys = int(m.group(1))
        elif cur_header:
            cur_body.append(line)
        else:
            head.append(line)
    close()

    out = list(head)
    for k, lines in blocks:
        if k is None or k in keys:
            out.extend(lines)
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--keys", type=int, action="append", default=None,
                    help="keep only these [Mania] key counts (repeatable)")
    args = ap.parse_args()

    info = slim(pathlib.Path(args.src), pathlib.Path(args.dst), set(args.keys) if args.keys else None)
    pct = info["kept_mb"] / info["whole_mb"] * 100 if info["whole_mb"] else 0
    print(f"{args.src}\n  -> {args.dst}")
    print(f"  {info['files']} files / {info['whole_mb']:.1f} MB  ->  "
          f"{info['kept']} files / {info['kept_mb']:.2f} MB  ({pct:.1f} %)")


if __name__ == "__main__":
    main()
