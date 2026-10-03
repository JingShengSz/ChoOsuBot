"""Inventory mania-relevant entries inside one or more .osk packages."""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

PATTERNS = [
    r"mania-hit", r"mania-note", r"mania-key", r"mania-stage",
    r"lighting", r"comboburst",
]


def inventory(path: Path) -> None:
    print("=" * 78)
    print(path.name)
    print("-" * 78)
    try:
        zf = zipfile.ZipFile(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  !! cannot open: {exc}")
        return
    names = zf.namelist()
    print(f"  entries: {len(names)}")

    # skin.ini files
    inis = [n for n in names if n.lower().replace("\\", "/").endswith("skin.ini")]
    print(f"  skin.ini files: {inis}")

    buckets: dict[str, list[str]] = {p: [] for p in PATTERNS}
    for n in names:
        low = n.lower().replace("\\", "/")
        for p in PATTERNS:
            if p in low:
                buckets[p].append(n)
                break

    for p, items in buckets.items():
        if not items:
            print(f"  [{p}] none")
            continue
        # collapse animation frames: name-<n>.png -> name
        groups: dict[str, list[str]] = {}
        for it in items:
            stem = re.sub(r"-\d+(?=\.[a-z]+$)", "", it)
            groups.setdefault(stem, []).append(it)
        print(f"  [{p}] {len(items)} files / {len(groups)} sprites")
        for stem in sorted(groups, key=str.lower):
            frames = groups[stem]
            sizes = []
            for f in sorted(frames)[:3]:
                try:
                    sizes.append(f"{zf.getinfo(f).file_size}B")
                except KeyError:
                    pass
            extra = f" (+{len(frames) - 3} more)" if len(frames) > 3 else ""
            print(f"      {stem}  x{len(frames)}  [{', '.join(sizes)}]{extra}")

    # print the [Mania] section of the root skin.ini
    root_inis = sorted(inis, key=lambda n: n.count("/") + n.count("\\"))
    if root_inis:
        raw = zf.read(root_inis[0]).decode("utf-8-sig", errors="replace")
        lines = raw.splitlines()
        grabbing = False
        print(f"  ---- [Mania] of {root_inis[0]} ----")
        for ln in lines:
            s = ln.strip()
            if s.startswith("["):
                grabbing = s.lower().startswith("[mania]")
                continue
            if grabbing and s and not s.startswith("//"):
                print("      " + s)


for arg in sys.argv[1:]:
    p = Path(arg)
    if p.is_file():
        inventory(p)
    else:
        print(f"missing: {p}")
