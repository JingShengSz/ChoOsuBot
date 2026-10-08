from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from .osu_file import parse_osu
from .models import OsuBeatmap

OSU_FILE_URL = "https://osu.ppy.sh/osu/{bid}"
SAYO_META = "https://api.sayobot.cn/ppy/get_beatmaps"
SAYO_AUDIO = "https://dl.sayobot.cn/beatmaps/files/{sid}/{name}"
# Direct per-file mirrors, tried in order before falling back to downloading the whole set.
FILE_MIRRORS = (
    SAYO_AUDIO,
    "https://api.nerinyan.moe/d/{sid}/{name}",
)
SAYO_MINI = "https://dl.sayobot.cn/beatmaps/download/mini/{sid}"

# The official download described by osu!lazer:
#   DownloadBeatmapSetRequest.Target => beatmapsets/{OnlineID}/download(?noVideo=1)
# it inherits APIDownloadRequest -> APIRequest, whose Perform() adds
#   Authorization: Bearer {API.AccessToken}
# and lazer's AccessToken only ever comes from the USER (authorization_code) flow.
# MEASURED with this project's own client_id/secret: client_credentials gets
# 200 text/html for every combination tried — Bearer + x-api-version, Bearer alone, and
# no Authorization at all returned byte-identical guest pages. So this source is wired up
# ONLY when a user token is present; without one it is skipped entirely rather than
# silently downloading an HTML error page.
OSU_OFFICIAL_OSZ = "https://osu.ppy.sh/beatmapsets/{sid}/download?noVideo=1"
_OSU_TOKEN_PATH = Path(__file__).resolve().parents[1] / "cache" / "osu_token.json"


def osu_user_token() -> str | None:
    """The configured USER access token, or None.

    Read from $OSU_USER_TOKEN first (deployment-friendly), else cache/osu_token.json as
    written by tools/osu_oauth.py.
    """
    env = (os.environ.get("OSU_USER_TOKEN") or "").strip()
    if env:
        return env
    try:
        data = json.loads(_OSU_TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    tok = str(data.get("access_token") or "").strip()
    return tok or None

# Mirror fallbacks. sayobot is the fastest when reachable, but it is not always up, and a
# single hard-coded host means no audio at all when it is down. Every entry is a
# beatmapset .osz download; the audio/background is then taken out of the archive.
OSZ_MIRRORS = (
    SAYO_MINI,
    "https://api.nerinyan.moe/d/{sid}?noVideo=1",
    "https://catboy.best/d/{sid}",
    "https://osu.direct/api/d/{sid}?noVideo=1",
    "https://beatconnect.io/b/{sid}/",
)
# NOTE (Linux deployment fix) — UA chosen by measurement, not by taste.
# osu.ppy.sh sits behind Cloudflare, which answered the previous spoofed UA with a
# 403 challenge page from this datacenter IP. Measured on the target host against
# every host this module talks to (HTTP code; osz rows use a 2 KB range request):
#
#   UA                                                    osu.ppy.sh  sayo  nerinyan-osz  catboy  osu.direct  beatconnect
#   Mozilla/5.0 (compatible; mania-render/0.1)  (was)       403 HTML   200      200        200      200         200
#   mania-render/0.1                          (chosen)      200 REAL   200      200        200      200         200
#   mania-render/0.1 (+https://github.com/)                 200 REAL   200      404        403      200         200
#   curl/7.81.0                                             200 REAL   200      200        403      200         200
#
# Two findings worth keeping: impersonating a browser is what gets blocked here
# (a real Chrome UA also 403s on osu.ppy.sh), and the seemingly-harmless
# "(+https://...)" suffix actually BREAKS two mirrors — the nerinyan osz download
# 404s and catboy 403s — which is exactly why every host was tested rather than one.
# The block is UA-triggered, not beatmap-specific: bids 1, 1000, 2084713 and
# 5358445 all 403 under the spoofed UA and all 200 under this one.
#
# Dl.sayobot.cn serves .osk/.mp3 via a 206 range response and is UA-agnostic;
# api.nerinyan.moe/d/<sid>/<name> returns 400 for every UA tried (pre-existing,
# unrelated to this change) — sayobot is tried first in FILE_MIRRORS, so audio
# resolution does not depend on it.
UA = "mania-render/0.1"


def _resolve_curl() -> str:
    """Absolute path to this platform's curl, or a loud, actionable error.

    The binary used to be hard-coded as `curl.exe`. On Linux that does not exist, so
    every `_curl()` call died with a bare
    `FileNotFoundError: [Errno 2] No such file or directory: 'curl.exe'`.
    `_http_text()` hid that behind a urllib fallback, but `_fetch_any_osz()`,
    `fetch_audio()` and `fetch_bg()` call `_curl()` directly and have no fallback, so
    audio and backgrounds could never be fetched off Windows at all.

    A missing curl is a deployment mistake the operator has to fix, so it is raised
    as a message that names the binary and the package to install — never as a bare
    FileNotFoundError buried in a plugin log.
    """
    names = ("curl.exe", "curl") if os.name == "nt" else ("curl", "curl.exe")
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError(
        "curl is required by mania-render (every beatmap / audio / background "
        "download shells out to it) but was not found on PATH. Looked for: "
        f"{', '.join(names)}. Install it — Debian/Ubuntu: `apt install curl`, "
        "Alpine: `apk add curl`, RHEL/Fedora: `dnf install curl`."
    )


_CURL_BIN: str | None = None


def _curl_bin() -> str:
    """Resolved lazily so importing this module never requires curl to be present.

    The static/API server (`--web`) does not download anything on the request path,
    so it must still start on a box where curl is missing; only an actual render
    should fail, and then with the message above.
    """
    global _CURL_BIN
    if _CURL_BIN is None:
        _CURL_BIN = _resolve_curl()
    return _CURL_BIN


def _curl(url: str, dest: Path | None = None, timeout: int = 90,
          headers: dict[str, str] | None = None) -> bytes:
    cmd = [_curl_bin(), "-sS", "--fail-with-body", "-L", "--max-time", str(timeout), "-A", UA]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    tmp: Path | None = None
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # `--fail-with-body` writes the server's ERROR BODY to curl's -o target even though it
        # then exits non-zero. Downloading straight to `dest` therefore left that error page
        # sitting at the final path, and because the audio/background caches are read back by
        # glob (`{sid}.*`) the 57-byte `{"error":"invalid_id"}` JSON was afterwards served as
        # `audio/mpeg` forever — the beatmap could never recover. Write aside, publish on
        # success only.
        tmp = dest.with_name(dest.name + ".part")
        cmd += ["-o", str(tmp)]
    cmd.append(url)
    try:
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
        except FileNotFoundError as exc:
            # Belt and braces: the binary resolved at startup can still vanish (uninstalled,
            # PATH changed, sandboxed service, wrong container image). Say which binary and
            # why, rather than leaking a bare FileNotFoundError into a plugin log.
            raise RuntimeError(
                f"curl binary {cmd[0]!r} could not be executed for {url}: {exc}. "
                "Install curl or make it visible on PATH for this service."
            ) from exc
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"download failed: {url} ({proc.returncode}) {err}")
        if dest is None:
            return proc.stdout
        tmp.replace(dest)          # atomic: `dest` never exists in a partial state
        return dest.read_bytes()
    finally:
        # A raised download must not leave anything behind on either path.
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _http_text(url: str) -> str:
    # curl first: Windows urllib→sayobot/ppy can block on TLS even with timeout
    try:
        return _curl(url, timeout=45).decode("utf-8", "replace")
    except Exception:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", "replace")


def fetch_meta(bid: str | None = None, sid: str | None = None, md5: str | None = None) -> list[dict]:
    import json

    if md5:
        url = f"{SAYO_META}?h={md5}"
    elif sid:
        url = f"{SAYO_META}?s={sid}"
    elif bid:
        url = f"{SAYO_META}?b={bid}"
    else:
        raise ValueError("need bid, sid or md5")
    data = json.loads(_http_text(url))
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"no metadata for {url}")
    return data


def lookup_bid_by_md5(md5: str, cache: Path | None = None) -> str | None:
    """Resolve beatmap id from file MD5. Local cache first, then sayobot API."""
    import hashlib

    if cache:
        osu_dir = cache / "osu"
        if osu_dir.is_dir():
            for p in osu_dir.glob("*.osu"):
                if hashlib.md5(p.read_bytes()).hexdigest() == md5.lower():
                    return p.stem
    try:
        rows = fetch_meta(md5=md5)
    except Exception:
        return None
    if rows:
        bid = str(rows[0].get("beatmap_id") or "").strip()
        return bid or None
    return None


def fetch_osu_text(bid: str) -> str:
    text = _http_text(OSU_FILE_URL.format(bid=bid))
    idx = text.find("osu file format")
    if idx < 0:
        raise RuntimeError(f"not a .osu for bid={bid}")
    return text[idx:] if idx else text


def _osz_sources(sid: str):
    """(label, url, headers) for every whole-set source, cheapest first.

    The official osu! download sits LAST — as a true last resort it costs a full-size .osz
    (tens of MB) where sayobot's mini archive is audio-only — and appears only when a user
    token is configured.
    """
    for tmpl in OSZ_MIRRORS:
        url = tmpl.format(sid=sid)
        yield urllib.parse.urlparse(url).netloc, url, None
    tok = osu_user_token()
    if tok:
        yield ("osu!official", OSU_OFFICIAL_OSZ.format(sid=sid),
               {"Authorization": f"Bearer {tok}", "x-api-version": "20220705",
                "Accept-Language": "en"})


def _fetch_any_osz(sid: str, osz: Path) -> str:
    """Download the beatmapset archive from the first mirror that answers."""
    errors = []
    for label, url, headers in _osz_sources(sid):
        try:
            _curl(url, osz, timeout=180, headers=headers)
            if osz.is_file() and osz.stat().st_size > 1024:
                return label
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
    hint = "" if osu_user_token() else (
        " | the official download was skipped: it needs a USER token "
        "($OSU_USER_TOKEN or cache/osu_token.json) — client credentials cannot download")
    raise RuntimeError("no mirror served the beatmapset: " + " | ".join(errors) + hint)


AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".flac", ".m4a")


def looks_like_audio(path: Path) -> bool:
    """Reject stub/error bodies that a failed download may have left behind.

    The audio cache is keyed by GLOB, not by a manifest, so whatever sits at `{sid}.mp3` is
    handed to the page as `audio/mpeg`. A 57-byte JSON error page is not a track, and
    treating it as one is what made a beatmap fail forever instead of once.
    """
    try:
        if not path.is_file() or path.stat().st_size < 4096:
            return False
        head = path.read_bytes()[:8].lstrip()
    except OSError:
        return False
    if head[:1] in (b"{", b"<", b"["):        # JSON / HTML error page
        return False
    # ID3 or bare MPEG sync, OggS, RIFF/WAVE, fLaC.
    return head[:3] in (b"ID3", b"Ogg") or head[:4] in (b"RIFF", b"fLaC") or head[:1] == b"\xff"


def audio_cache_path(cache: Path, sid: str, audio_filename: str) -> Path:
    """A set may contain several songs; cache each named track separately."""
    normalized = audio_filename.strip().replace("\\", "/")
    key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    ext = Path(normalized).suffix.lower() or ".mp3"
    return cache / "audio" / f"{sid}-{key}{ext}"


def fetch_audio(sid: str, audio_filename: str, dest: Path) -> Path:
    name = urllib.parse.quote(audio_filename)
    # NOTE (fresh-deployment fix): a new install has no cache/audio directory yet. The
    # direct-mirror loop below goes through _curl(), which creates dest.parent, but the
    # whole-set (osz) fallback further down writes straight to `dest` and would raise
    # FileNotFoundError on a clean checkout. Create the directory once, up front, so
    # every write path in here can assume it exists.
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Drop a poisoned entry left by an earlier failure so it cannot satisfy the checks below.
    if dest.is_file() and not looks_like_audio(dest):
        try:
            dest.unlink()
        except OSError:
            pass
    for tmpl in FILE_MIRRORS:
        try:
            _curl(tmpl.format(sid=sid, name=name), dest, timeout=90)
            if looks_like_audio(dest):
                return dest
        except Exception:
            continue
    if True:   # direct mirrors exhausted -> fetch the whole set
        # fallback mini osz
        import tempfile
        import zipfile

        tmp = Path(tempfile.mkdtemp(prefix="mr_audio_"))
        osz = tmp / f"{sid}.osz"
        try:
            _fetch_any_osz(sid, osz)
            want = Path(audio_filename).name.lower()
            with zipfile.ZipFile(osz) as zf:
                for n in zf.namelist():
                    if Path(n).name.lower() == want:
                        dest.write_bytes(zf.read(n))
                        if looks_like_audio(dest):
                            return dest
        except Exception:
            pass
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            # Never leave a stub behind for the glob to serve later.
            if dest.is_file() and not looks_like_audio(dest):
                try:
                    dest.unlink()
                except OSError:
                    pass
        raise RuntimeError(f"audio {audio_filename!r} not found in set {sid}")


def fetch_bg(sid: str, bg_filename: str, dest: Path) -> Path:
    """Download the named original background, never an arbitrary set image."""
    bg_filename = bg_filename.replace("\\", "/")
    name = urllib.parse.quote(bg_filename)
    # See fetch_audio: the osz fallback writes straight to `dest`, bypassing the
    # _curl() call that is otherwise the only creator of the parent directory.
    dest.parent.mkdir(parents=True, exist_ok=True)
    for tmpl in FILE_MIRRORS:
        try:
            _curl(tmpl.format(sid=sid, name=name), dest, timeout=90)
            if looks_like_image(dest):
                return dest
        except Exception:
            continue
    import tempfile
    import zipfile
    with tempfile.TemporaryDirectory(prefix="mr_bg_") as directory:
        tmp = Path(directory)
        osz = tmp / f"{sid}.osz"
        _fetch_any_osz(sid, osz)
        with zipfile.ZipFile(osz) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            matches = [n for n in names if n.replace("\\", "/").casefold() == bg_filename.casefold()]
            if not matches:
                matches = [n for n in names if n.replace("\\", "/").rsplit("/", 1)[-1].casefold()
                           == bg_filename.rsplit("/", 1)[-1].casefold()]
            if len(matches) == 1:
                dest.write_bytes(zf.read(matches[0]))
                if looks_like_image(dest):
                    return dest
        raise RuntimeError(f"background {bg_filename!r} not found in set {sid}")


def looks_like_image(path: Path) -> bool:
    """Reject HTML/JSON error pages without adding a Pillow dependency to OM."""
    try:
        with Path(path).open("rb") as stream:
            head = stream.read(32)
        return (head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM"))
                or (head.startswith(b"RIFF") and head[8:12] == b"WEBP"))
    except OSError:
        return False


def get_background(sid: str, filename: str, cache: Path) -> Path:
    """Shared OM/card entry point: original file, validated cache, mirror/OSZ fallback.

    Raises on failure. The key includes the full filename because difficulties in
    one beatmapset may use different images. This does not download audio.
    """
    sid = str(sid)
    if not re.fullmatch(r"[0-9]+", sid) or not filename.strip():
        raise ValueError("A numeric beatmapset ID and background filename are required")
    filename = filename.replace("\\", "/")
    key = hashlib.sha256(filename.encode()).hexdigest()[:20]
    ext = Path(filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
        ext = ".img"
    dest = Path(cache) / "backgrounds" / f"{sid}_{key}{ext}"
    if looks_like_image(dest):
        return dest
    # Download to a unique staging file so concurrent requests cannot publish a
    # partial download or delete another request's work.
    import tempfile
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bg_", dir=dest.parent) as directory:
        stage = Path(directory) / dest.name
        fetch_bg(sid, filename, stage)
        if not looks_like_image(stage):
            raise RuntimeError("Background response was not an image")
        stage.replace(dest)
    return dest


def get_beatmap_background(bid: str, cache: Path) -> Path | None:
    """Resolve .osu Events -> original background. None means no declared image."""
    bid = str(bid)
    if not re.fullmatch(r"[0-9]+", bid):
        raise ValueError("A numeric beatmap ID is required")
    osu_path = Path(cache) / "osu" / f"{bid}.osu"
    if not osu_path.is_file():
        osu_path.parent.mkdir(parents=True, exist_ok=True)
        osu_path.write_text(fetch_osu_text(bid), encoding="utf-8")
    bm = parse_osu(osu_path.read_text(encoding="utf-8", errors="replace"))
    if not bm.background_filename:
        return None
    sid = bm.beatmapset_id
    if not sid:
        rows = fetch_meta(bid=bid)
        sid = str(rows[0].get("beatmapset_id") or "")
    return get_background(sid, bm.background_filename, cache)


def load_beatmap_by_id(
    bid: str,
    cache: Path,
    osu_override: Path | None = None,
    audio_override: Path | None = None,
    bg_override: Path | None = None,
) -> tuple[OsuBeatmap, Path, Path | None]:
    osu_path = cache / "osu" / f"{bid}.osu"
    if osu_override:
        text = Path(osu_override).read_text(encoding="utf-8", errors="replace")
    else:
        if not osu_path.is_file():
            # NOTE (fresh-deployment fix): `cache/osu` does not exist on a clean install,
            # so this write_text raised
            #   FileNotFoundError: [Errno 2] No such file or directory: '.../cache/osu/<bid>.osu'
            # and the CLI could not render a bid at all. webapp.py:736 already guards its
            # own equivalent write; this brings the CLI path in line with it.
            osu_path.parent.mkdir(parents=True, exist_ok=True)
            osu_path.write_text(fetch_osu_text(bid), encoding="utf-8")
        text = osu_path.read_text(encoding="utf-8", errors="replace")

    bm = parse_osu(text)
    sid = bm.beatmapset_id
    if not sid:
        # resolve via sayobot
        rows = fetch_meta(bid=bid)
        sid = str(rows[0].get("beatmapset_id") or "")
        bm.beatmapset_id = sid
        if not bm.title:
            bm.title = str(rows[0].get("title") or "")
        if not bm.artist:
            bm.artist = str(rows[0].get("artist") or "")

    if audio_override:
        audio_path = Path(audio_override)
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)
    else:
        audio_path = audio_cache_path(cache, sid, bm.audio_filename)
        if not audio_path.is_file():
            fetch_audio(sid, bm.audio_filename, audio_path)

    bg_path: Path | None = None
    if bg_override:
        bg_path = Path(bg_override)
        if not bg_path.is_file():
            raise FileNotFoundError(bg_path)
    elif bm.background_filename:
        try:
            bg_path = get_background(sid, bm.background_filename, cache)
        except Exception as exc:
            print(f"[warn] background fetch failed: {exc}", file=sys.stderr)
            bg_path = None

    return bm, audio_path, bg_path


def parse_range(spec: str) -> tuple[float, float]:
    """Parse '0-100' closed interval seconds."""
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*-\s*([0-9]*\.?[0-9]+)\s*", spec)
    if not m:
        raise ValueError(f"invalid range: {spec!r} (expected start-end)")
    a, b = float(m.group(1)), float(m.group(2))
    if b < a:
        raise ValueError(f"range end < start: {spec!r}")
    return a, b
