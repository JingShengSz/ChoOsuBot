"""How much of a .osk does the mania renderer actually need?

This is the number behind the "slim the skin before sending it" recommendation: the whole
archive has to be downloaded, unzipped and decoded by whoever renders, and only a little of
it is ever referenced.
"""
from __future__ import annotations

import pathlib
import re
import zipfile

CORE_PREFIXES = (
    "mania-note", "mania-key", "mania-stage-", "mania-hit", "mania-stage-light",
    "mania-stage-hint", "mania-warningarrow", "lighting", "comboburst",
)
ALWAYS = {"skin.ini", "mainhudcomponents.json", "playfield.json"}
INI_KEYS = {
    "lightingn", "lightingl", "stagelight", "stagehint", "leftstageimage",
    "rightstageimage", "bottomstageimage", "warningarrow",
}


def scan(path: pathlib.Path) -> tuple[float, float, int, int]:
    with zipfile.ZipFile(path) as z:
        total = sum(e.file_size for e in z.infolist())
        keep = 0
        kept = 0
        for e in z.infolist():
            if e.is_dir():
                continue
            low = e.filename.replace("\\", "/").lower()
            base = pathlib.PurePosixPath(low).name
            stem = pathlib.PurePosixPath(low).stem
            core = re.sub(r"@2x$", "", stem)
            core = re.sub(r"-\d+$", "", core)
            if base in ALWAYS or any(core.startswith(p) for p in CORE_PREFIXES):
                keep += e.file_size
                kept += 1
        return total / 1048576, keep / 1048576, kept, len(z.infolist())


def main() -> None:
    root = pathlib.Path(r"D:\osu-lazer\exports")
    print(f"{'skin':<38}{'whole':>10}{'wanted':>10}{'keep':>8}{'files':>12}")
    for f in sorted(root.glob("*.osk"), key=lambda p: -p.stat().st_size):
        try:
            tot, keep, kept, n = scan(f)
        except Exception as exc:  # noqa: BLE001
            print(f"{f.name[:36]:<38}  ERROR {exc}")
            continue
        pct = (keep / tot * 100) if tot else 0
        print(f"{f.name[:36]:<38}{tot:9.1f}M{keep:9.1f}M{pct:7.1f}%{kept:6d}/{n:<5d}")


if __name__ == "__main__":
    main()
