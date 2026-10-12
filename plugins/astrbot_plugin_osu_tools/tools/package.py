"""Package an explicit allowlist; never include data, credentials or environments."""

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "main.py",
    "command_filter.py",
    "api.py",
    "catalog.py",
    "output.py",
    "api_catalog.json",
    "metadata.yaml",
    "_conf_schema.json",
    "requirements.txt",
    "README.md",
]


def package(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    files = [ROOT / name for name in FILES]
    files += sorted((ROOT / "docs").glob("*.md"))
    files += sorted((ROOT / "tools").glob("*.py"))
    files += sorted((ROOT / "tests").glob("*.py"))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(Path(ROOT.name) / path.relative_to(ROOT)))
    if target.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("AstrBot ZIP size limit exceeded")
    print(f"{target}: {target.stat().st_size} bytes, {len(files)} files")


if __name__ == "__main__":
    package(Path(sys.argv[1]))
