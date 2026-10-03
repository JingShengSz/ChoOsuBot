"""Why does the command registry look empty? Dump what the framework actually holds."""
from __future__ import annotations

import importlib.util
import inspect
import pathlib

PLUGIN = pathlib.Path(__file__).resolve().parents[1] / "astrbot_plugin_mania_render" / "main.py"

spec = importlib.util.spec_from_file_location("mania_plugin_under_test", PLUGIN)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

cls = mod.ManiaRenderPlugin
print("=== attribute types on the class ===")
for name in ("om", "om_skins", "om_defaults", "render_mania_video", "terminate"):
    fn = getattr(cls, name, None)
    if fn is None:
        print(f"  {name:<20} MISSING")
        continue
    print(f"  {name:<20} type={type(fn).__name__:<12} "
          f"coro={inspect.iscoroutinefunction(fn)} "
          f"has_filters={hasattr(fn, 'event_filters')}")

print("\n=== star_handlers_registry contents ===")
from astrbot.core.star.star_handler import star_handlers_registry

items = list(star_handlers_registry)
print(f"  total handlers: {len(items)}")
for h in items:
    mod_path = str(getattr(h, "handler_module_path", "") or "")
    if "mania_render" in mod_path or "mania_plugin_under_test" in mod_path:
        filters = []
        for f in getattr(h, "event_filters", []):
            cn = getattr(f, "command_name", None)
            filters.append(f"{type(f).__name__}({cn})" if cn else type(f).__name__)
        print(f"  FOUND {h.handler_name:<22} module={mod_path!r} filters={filters}")

print("\n  (module paths seen in the registry, unique, first 12)")
seen = []
for h in items:
    mp = str(getattr(h, "handler_module_path", "") or "")
    if mp and mp not in seen:
        seen.append(mp)
for mp in seen[:12]:
    print(f"    {mp}")
