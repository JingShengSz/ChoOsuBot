"""Confirm the framework actually registered `om` — not just that the file imported.

    D:\\LLBot\\bin\\astrbot\\.venv\\Scripts\\python.exe tools/plugin_registry_check.py
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

PLUGIN = pathlib.Path(__file__).resolve().parents[1] / "astrbot_plugin_mania_render" / "main.py"


def main() -> int:
    spec = importlib.util.spec_from_file_location("mania_plugin_under_test", PLUGIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from astrbot.core.star.filter.command import CommandFilter
    from astrbot.core.star.star_handler import star_handlers_registry
    import astrbot.core.star.register as register

    names = []
    for handler in star_handlers_registry:
        md = getattr(handler, "handler_module_path", "") or ""
        if "mania" not in str(md):
            continue
        filters = [type(f).__name__ for f in getattr(handler, "event_filters", [])]
        cmd = ""
        for f in getattr(handler, "event_filters", []):
            if isinstance(f, CommandFilter):
                cmd = f.command_name
        names.append((cmd or handler.handler_name, handler.handler_name, filters))

    if not names:
        print("NOT REGISTERED: the registry holds no handler from this plugin")
        return 1
    print(f"registered handlers: {len(names)}")
    for cmd, fn, filters in names:
        print(f"  command {cmd!r:<14} -> {fn:<22} filters={filters}")

    # tool registration happens through the provider tool manager
    try:
        from astrbot.core.provider.func_tool_manager import FunctionToolManager

        print("\nllm tools are added at star-load time (see the 'Added llm tool' log line).")
        print("FunctionToolManager import ok:", FunctionToolManager.__name__)
    except Exception as exc:
        print("could not import FunctionToolManager:", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
