"""Build a targeted AstrBot patch without replacing unrelated core changes."""

import argparse
import ast
from pathlib import Path


def build_patch(source: str) -> str:
    """Replace only request-round truncation methods in the upstream class.

    Args:
        source: The installed truncator source text.

    Returns:
        Updated source with the existing message repair logic preserved.

    Raises:
        ValueError: When the installed source does not expose the expected methods.
    """
    replacements = Path(__file__).with_name("methods.py").read_text(encoding="utf-8")
    replacement_lines = replacements.splitlines(keepends=True)
    methods = next(
        node for node in ast.parse(replacements).body if isinstance(node, ast.ClassDef)
    )
    blocks = {
        node.name: "".join(replacement_lines[node.lineno - 1 : node.end_lineno])
        for node in methods.body
        if isinstance(node, ast.FunctionDef)
    }
    tree = ast.parse(source)
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ContextTruncator"
    )
    existing = {
        node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)
    }
    needed = set(blocks) - {"_split_request_rounds"}
    if not needed.issubset(existing) or "fix_messages" not in existing:
        raise ValueError(
            "Unsupported AstrBot truncator; inspect the new version first."
        )
    lines = source.splitlines(keepends=True)
    for name, node in sorted(
        existing.items(), key=lambda item: item[1].lineno, reverse=True
    ):
        if name in blocks:
            lines[node.lineno - 1 : node.end_lineno] = [blocks[name]]
    result = "".join(lines)
    if "_split_request_rounds" not in existing:
        result += "\n\n" + blocks["_split_request_rounds"] + "\n"
    ast.parse(result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        build_patch(args.source.read_text(encoding="utf-8")), encoding="utf-8"
    )
    print(f"Built request-round patch: {args.output.name}")
