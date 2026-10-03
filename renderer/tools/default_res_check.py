"""Assert the plugin's effective render size under several configs.

    python tools/default_res_check.py

Instantiates the real plugin class under AstrBot's own interpreter, so the
check exercises the shipped `_resolution()` rather than a copy of its logic.
"""
from __future__ import annotations

import os
import sys

ASTRBOT_ROOT = os.environ.get("ASTRBOT_ROOT", r"D:\LLBot\bin\astrbot")
PLUGIN_DIR = os.path.join(
    ASTRBOT_ROOT, "data", "plugins", "astrbot_plugin_mania_render"
)

sys.path.insert(0, ASTRBOT_ROOT)
sys.path.insert(0, PLUGIN_DIR)

from main import (  # noqa: E402  (path set up above on purpose)
    DEFAULT_HEIGHT,
    DEFAULT_RESOLUTION,
    DEFAULT_WIDTH,
    ManiaRenderPlugin,
)

CASES = [
    ({}, {}, (1920, 1080), "no config, no -r  -> 1080p default"),
    ({}, {"width": 1280, "height": 720}, (1280, 720), "-r 720 wins over the default"),
    ({}, {"width": 1920, "height": 1080}, (1920, 1080), "-r 1080 explicit"),
    ({"default_resolution": "720"}, {}, (1280, 720), "config drops the default to 720p"),
    ({"default_resolution": "720p"}, {}, (1280, 720), "'720p' spelling accepted"),
    ({"default_resolution": "nonsense"}, {}, (1920, 1080), "bad config falls back to 1080p"),
]


def main() -> int:
    print(f"module defaults: DEFAULT_RESOLUTION={DEFAULT_RESOLUTION!r} "
          f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
    ok = True
    for config, opts, want, label in CASES:
        plugin = ManiaRenderPlugin(context=None, config=config)
        got = plugin._resolution(opts)
        good = got == want
        ok &= good
        print(f"  {'OK  ' if good else 'FAIL'} {label:<34} -> {got[0]}x{got[1]}  (want {want[0]}x{want[1]})")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
