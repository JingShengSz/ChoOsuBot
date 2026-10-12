"""Install the pinned official MRM release and compile our noninteractive bridge."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mania_render.mrm_render import RELEASE_URL, RELEASE_SHA256, JAR_SHA256, java_tool  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, help='Already downloaded official v2.4.0 ZIP')
    args = parser.parse_args()
    home = Path(os.environ.get('MANIA_MRM_HOME') or ROOT / 'vendor/mania-replay-master')
    home.mkdir(parents=True, exist_ok=True)
    archive = args.archive or home / 'release.zip'
    if not args.archive and not archive.is_file():
        urllib.request.urlretrieve(RELEASE_URL, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != RELEASE_SHA256:
        raise RuntimeError('Official release archive SHA256 mismatch')
    with zipfile.ZipFile(archive) as package:
        names = [n for n in package.namelist() if n.endswith('/ManiaReplayMaster.jar')]
        if len(names) != 1:
            raise RuntimeError('Missing MRM jar')
        body = package.read(names[0])
    if hashlib.sha256(body).hexdigest() != JAR_SHA256:
        raise RuntimeError('Official jar SHA256 mismatch')
    jar = home / 'ManiaReplayMaster.jar'
    jar.write_bytes(body)
    source = ROOT / 'mrm_bridge/Bridge.java'
    classes = home / 'classes'
    classes.mkdir(exist_ok=True)
    subprocess.run([java_tool('javac'), '--release', '8', '-encoding', 'UTF-8',
                    '-cp', str(jar), '-d', str(classes), str(source)], check=True)
    (home / 'bridge.sha256').write_text(hashlib.sha256(source.read_bytes()).hexdigest())
    print('Installed Mania-Replay-Master v2.4.0 and compiled bridge')


if __name__ == '__main__':
    main()
