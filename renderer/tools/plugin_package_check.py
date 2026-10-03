"""Validate the AstrBot plugin package against the developer manual's checklist.

    python tools/plugin_package_check.py

Metadata is checked the way AstrBot itself checks it: `name`, `desc`, `version`
and `author` must all be *non-empty strings*. A present-but-empty `author: ""`
makes AstrBot raise `插件元数据校验失败` and the plugin never reaches the
WebUI plugin list -- and on a first import the exception is downgraded to a
warning, so the plugin loads with `name=None` and `is_ghost_plugin()` then
hides it from the list entirely. Silence, not an error. Hence this check.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

PLUGIN = pathlib.Path(__file__).resolve().parents[1] / "astrbot_plugin_mania_render"
REQUIRED = ("main.py", "metadata.yaml", "requirements.txt", "README.md", "_conf_schema.json")

# Mirrors PLUGIN_METADATA_REQUIRED_FIELDS in astrbot/core/star/updater.py
METADATA_REQUIRED = ("name", "desc", "version", "author")


def _top_level_scalars(text: str) -> dict[str, str]:
    """Parse top-level `key: value` pairs, expanding `|`/`>` block scalars."""
    out: dict[str, str] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line[:1] in " \t#":
            i += 1
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):(.*)$", line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest in ("|", "|-", "|+", ">", ">-", ">+"):
            block = []
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i][:1] in " \t"):
                block.append(lines[i].strip())
                i += 1
            out[key] = "\n".join(block).strip()
            continue
        out[key] = rest.strip().strip('"').strip("'")
        i += 1
    return out


def _astrbot_root() -> pathlib.Path | None:
    """Locate an AstrBot checkout so the real validator can be used."""
    for candidate in (
        os.environ.get("ASTRBOT_ROOT"),
        r"D:\LLBot\bin\astrbot",
        str(pathlib.Path.home() / "astrbot"),
    ):
        if candidate and (pathlib.Path(candidate) / "astrbot" / "core" / "star" / "updater.py").is_file():
            return pathlib.Path(candidate)
    return None


def _real_validation(meta_text: str) -> tuple[bool, str]:
    """Run AstrBot's own validate_plugin_metadata when a checkout is available."""
    root = _astrbot_root()
    if root is None:
        return False, "no AstrBot checkout found; used the mirrored rule only"
    entry = str(root)
    sys.path.insert(0, entry)
    try:
        from astrbot.core.star.updater import _PluginUpdater  # type: ignore

        try:
            import yaml  # type: ignore

            parsed = yaml.safe_load(meta_text)
        except Exception:
            parsed = _top_level_scalars(meta_text)
        _PluginUpdater.validate_plugin_metadata(parsed, "metadata.yaml")
        return True, f"accepted by AstrBot's own validator ({root})"
    except Exception as exc:  # noqa: BLE001 - report any validator verdict verbatim
        return False, str(exc)
    finally:
        if entry in sys.path:
            sys.path.remove(entry)


def main() -> int:
    ok = True
    print("files")
    for name in REQUIRED:
        p = PLUGIN / name
        exists = p.is_file()
        ok &= exists
        size = p.stat().st_size if exists else 0
        print(f"  {'OK ' if exists else 'MISS'} {name:<20} {size:>7} bytes")

    print("\nmetadata.yaml")
    meta_text = (PLUGIN / "metadata.yaml").read_text(encoding="utf-8")
    meta = _top_level_scalars(meta_text)
    print(f"  parsed {len(meta)} top-level keys: {', '.join(meta)}")

    # AstrBot rule: required fields must exist AND be non-empty strings.
    for field in METADATA_REQUIRED:
        value = meta.get(field)
        good = isinstance(value, str) and bool(value.strip())
        ok &= good
        shown = repr(value)[:60] if value is not None else "<missing>"
        print(f"  {'OK ' if good else 'FAIL'} {field:<8} non-empty string  {shown}")

    astrbot_ok, verdict = _real_validation(meta_text)
    print(f"  {'OK ' if astrbot_ok else 'FAIL'} AstrBot validator: {verdict}")
    ok &= astrbot_ok

    name_match = meta.get("name") == PLUGIN.name
    ok &= name_match
    print(f"  {'OK ' if name_match else 'FAIL'} directory name matches metadata name ({PLUGIN.name})")

    version = meta.get("version", "")
    semver = bool(re.fullmatch(r"\d+\.\d+\.\d+", version))
    ok &= semver
    print(f"  {'OK ' if semver else 'FAIL'} version is semver  ({version or '?'})")

    display_name = meta.get("display_name", "")
    has_display = bool(display_name.strip())
    ok &= has_display
    print(f"  {'OK ' if has_display else 'FAIL'} display_name set  ({display_name or '<missing>'})")

    print("\n_conf_schema.json")
    try:
        schema = json.loads((PLUGIN / "_conf_schema.json").read_text(encoding="utf-8"))
        bad = [k for k, v in schema.items() if "type" not in v]
        print(f"  parses, {len(schema)} keys, every key has a type: {not bad}")
        ok &= not bad
    except Exception as exc:
        print(f"  FAILED: {exc}")
        ok = False

    print("\nmain.py")
    src = (PLUGIN / "main.py").read_text(encoding="utf-8")
    checks = {
        "inherits Star": "class ManiaRenderPlugin(Star)" in src,
        "super().__init__(context)": "super().__init__(context)" in src,
        "filter from astrbot.api.event": "from astrbot.api.event import AstrMessageEvent, filter" in src,
        "no requests library": "import requests" not in src,
        "aiohttp used": "import aiohttp" in src,
        "no register_llm_tool": "register_llm_tool" not in src,
        "no context.get_platform(": "context.get_platform(" not in src,
        "writes to plugin_data": 'get_astrbot_data_path' in src,
        "command names have no spaces": not any(
            " " in c for c in re.findall(r'@filter\.command\("([^"]+)"', src)
        ),
        "every handler has a docstring": all(
            bool(re.search(rf'async def {fn}\(.*?\):\n\s+"""(.*?)"""', src, re.S))
            for fn in ("om", "om_skins", "om_defaults", "render_mania_video")
        ),
        "reply-to-osr plumbing present": "_fetch_replied_osr" in src and "get_msg" in src,
        "llm_tool has Args:": "Args:" in src,
        "llm_tool Args entries look right": bool(
            re.search(r"Args:\n(?:.*\n)*?\s+(\w+)\((string|number|object|boolean|array)\):", src)
        ),
    }
    for label, passed in checks.items():
        print(f"  {'OK ' if passed else 'FAIL'} {label}")
        ok &= passed

    print("\ncommands and tool")
    for name in re.findall(r'@filter\.command\("([^"]+)"', src):
        print(f"  command : {name}")
    for name in re.findall(r'@filter\.llm_tool\(name="([^"]+)"', src):
        print(f"  tool    : {name}")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
