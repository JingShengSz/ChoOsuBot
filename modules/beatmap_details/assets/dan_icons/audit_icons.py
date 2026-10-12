"""Report which estimator interval labels have matching local dan artwork."""
from __future__ import annotations

import re
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
INTERVALS = HERE.parent.parent / "upstream" / "ManiaMapAnalyser by Leo_Black" / "js" / "estimator" / "intervals"
LABEL_RE = re.compile(r'\[\s*[\d.]+\s*,\s*[\d.]+\s*,\s*"([^"]+)"\s*\]')
SUFFIX_RE = re.compile(r"\s+(?:mid/high|mid/low|high|mid|low)$", re.I)


def icon_for(label: str) -> str | None:
    base = SUFFIX_RE.sub("", label).strip()
    lower = base.lower()
    if lower.startswith(("hypersovae ln ", "lnlism ln ")):
        lower = "ln" + lower.rsplit(" ", 1)[-1]
    if lower.startswith("thaumiel "):
        lower = lower.removeprefix("thaumiel ")
    elif lower.startswith("emik "):
        lower = lower.removeprefix("emik ")
    elif lower.startswith("cloverwisp "):
        lower = lower.removeprefix("cloverwisp ")
    if lower.startswith("ln "):
        lower = "ln" + lower[3:]
    if lower.startswith("vibro "):
        lower = "v" + lower[6:]
    return lower.replace(" ", "")


def write_manifest() -> None:
    from PIL import Image

    bounds = {}
    for source in sorted(HERE.glob("*.webp")):
        with Image.open(source) as image:
            box = image.convert("RGBA").getchannel("A").getbbox()
        if box:
            bounds[source.stem] = box
    target = HERE / "icon_manifest.js"
    target.write_text("window.DAN_ICON_BOUNDS = " + json.dumps(bounds, separators=(",", ":")) + ";\n",
                      encoding="utf-8")
    print(f"Wrote {target.name}: {len(bounds)} icons")


def main() -> None:
    if "--write-manifest" in sys.argv:
        write_manifest()
    labels = {match.group(1)
              for source in INTERVALS.glob("*.js")
              for match in LABEL_RE.finditer(source.read_text(encoding="utf-8"))}
    bases = sorted({SUFFIX_RE.sub("", label).strip() for label in labels}, key=str.casefold)
    missing = [(base, icon_for(base)) for base in bases
               if not (HERE / f"{icon_for(base)}.webp").is_file()]
    print(f"{len(labels)} interval labels, {len(bases)} base ranks")
    print(f"{len(missing)} without local artwork:")
    for base, icon in missing:
        print(f"  {base} -> {icon}.webp")


if __name__ == "__main__":
    main()
