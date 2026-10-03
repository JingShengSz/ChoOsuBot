"""Exercise the plugin's option parser without needing AstrBot installed.

    python tools/plugin_arg_selftest.py
"""
from __future__ import annotations

import pathlib
import re

MAIN = pathlib.Path(__file__).resolve().parents[1] / "astrbot_plugin_mania_render" / "main.py"


def load_helpers() -> dict:
    src = MAIN.read_text(encoding="utf-8")
    ns: dict = {"re": re}
    # the module-level constants the two helpers read
    for name in ("RESOLUTIONS", "DEFAULT_FPS", "DEFAULT_WIDTH", "DEFAULT_HEIGHT",
                 "DEFAULT_SCROLL", "DEFAULT_BG_DIM"):
        m = re.search(rf"^{name} = (\{{[^}}]*\}}|[^\n]+)", src, re.M)
        if m:
            exec(f"{name} = {m.group(1)}", ns)  # noqa: S102
    # `_parse_options` reads `ManiaRenderPlugin.BARE_ALIASES` off the class
    m = re.search(r"    BARE_ALIASES = \{.*?\n    \}", src, re.S)
    if not m:
        raise SystemExit("could not find BARE_ALIASES in main.py")
    bare_src = "\n".join(line[4:] if line.startswith("    ") else line
                         for line in m.group(0).splitlines())
    exec(bare_src, ns)  # noqa: S102
    ns["ManiaRenderPlugin"] = type("ManiaRenderPlugin", (), {"BARE_ALIASES": ns["BARE_ALIASES"]})
    for name in ("_parse_options", "_normalise"):
        m = re.search(rf"    @staticmethod\n    def {name}\(.*?\n(?=    @|    async def|    def )", src, re.S)
        if not m:
            raise SystemExit(f"could not find {name} in main.py")
        body = m.group(0).replace("    @staticmethod\n", "")
        body = "\n".join(line[4:] if line.startswith("    ") else line for line in body.splitlines())
        exec(body, ns)  # noqa: S102 - deliberate: the point is to test the real source
    return ns


CASES = [
    ("2467450 -s R Skin -d 30 -v 25", "full flag form"),
    ("2467450 skin=boj bgdim=0.3 res=1080 fps=30", "key=value form"),
    ("-s Cho 2467450", "flags before the id"),
    ("2467450 --from 60 --to 75", "time range"),
    ("R Skin 2467450", "bare skin name + id"),
    ("2467450 暗度 30", "Chinese aliases"),
    ("2467450 -d", "missing value -> error"),
    ("2467450 -v 99", "scroll out of range -> error"),
    ("2467450 -r 480", "bad resolution -> error"),
    ("2467450 --from 30 --to 10", "end before start -> error"),
    ("abc", "no id -> caller handles"),
]


def main() -> None:
    ns = load_helpers()
    parse, normalise = ns["_parse_options"], ns["_normalise"]
    for raw, label in CASES:
        opts, err = parse(raw)
        if err:
            print(f"{label:34} {raw!r:44} -> parse error: {err}")
            continue
        norm, err2 = normalise(opts)
        out = f"ERR: {err2}" if err2 else str(norm)
        print(f"{label:34} {raw!r:44} -> {out}")


if __name__ == "__main__":
    main()
