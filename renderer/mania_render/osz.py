"""Local beatmap packages, referenced by opaque IDs without extracting archive paths."""
import csv
import hashlib
import io
import json
import re
import uuid
import zipfile
from urllib.parse import unquote
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1] / 'cache' / 'packages'
ID_RE = re.compile(r'^local-[0-9a-f]{32}-[0-9]+$')

def is_local(value):
    return bool(ID_RE.fullmatch(str(value)))

def manifest(bid):
    if not is_local(bid): raise ValueError('Invalid local beatmap ID')
    return json.loads((ROOT / (str(bid) + '.json')).read_text(encoding='utf-8'))

def asset(bid, filename):
    m = manifest(bid)
    path = m['assets'].get(filename) or m['assets'].get(unquote(filename))
    if not path: raise FileNotFoundError('Package asset not found')
    return ROOT / path

def text(bid):
    return asset(bid, 'map.osu').read_text(encoding='utf-8')

def find_by_md5(md5):
    """Resolve only an exact uploaded chart hash; never guess by title."""
    if not re.fullmatch(r'[0-9a-f]{32}', str(md5).lower()): return None
    candidates = sorted(ROOT.glob('local-*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            meta = json.loads(path.read_text(encoding='utf-8'))['meta']
            if meta.get('chart_md5') == md5.lower(): return meta['beatmap_id']
        except (OSError, ValueError, KeyError): continue
    return None

def matches_converted_mrv(bid, replay):
    """Verify an osu source against V's converted chart, without trusting its title alone."""
    from .osu_file import parse_osu
    m = manifest(bid)['meta']
    def normalize(s):
        return ' '.join(str(s).casefold().split())
    if m.get('source') == 'malody':
        return False
    if normalize(m.get('title')) != normalize(replay.get('title')):
        return False
    if normalize(m.get('version')) != normalize(replay.get('difficulty')):
        return False
    bm = parse_osu(text(bid))
    rows = replay.get('recorded_judgements', [])
    if not rows or len(bm.hit_objects) != len(rows):
        return False
    if any(not 0 <= row['key'] < bm.keys for row in rows):
        return False
    for column in range(bm.keys):
        notes = sorted(n.start_time for n in bm.hit_objects if n.column == column)
        stamps = sorted(row['time'] for row in rows if row['key'] == column)
        if len(notes) != len(stamps) or any(abs(a-b) > 150 for a,b in zip(notes, stamps)):
            return False
    return True

def find_converted_mrv(replay):
    """Require a unique chart hash after checking every lane's recorded timeline."""
    matches = {}
    candidates = sorted(ROOT.glob('local-*.json'), key=lambda p:p.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            bid = path.stem
            if matches_converted_mrv(bid, replay):
                md5 = manifest(bid)['meta']['chart_md5']
                matches.setdefault(md5, bid)
        except (OSError, ValueError, KeyError):
            continue
    if len(matches) > 1:
        raise ValueError('多个 osu 谱面符合 MRV 时间线，请回复指定谱面包选择难度后渲染')
    return next(iter(matches.values()), None)

def import_package(data, *, require_audio=True):
    if len(data) > 150 * 1024**2: raise ValueError('osz 文件超过150MB')
    token = uuid.uuid4().hex
    ROOT.mkdir(parents=True, exist_ok=True)
    result = []
    warnings = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        infos = z.infolist()
        if len(infos) > 5000 or sum(i.file_size for i in infos) > 512 * 1024**2:
            raise ValueError('谱面包解压大小过大')
        names = {}
        for i in infos:
            n = i.filename.replace(chr(92), '/')
            if n.startswith('/') or '..' in PurePosixPath(n).parts:
                raise ValueError('谱面包包含不合法路径')
            if not i.is_dir(): names[n.casefold()] = i
        def read(n):
            info = names.get(n.replace(chr(92), '/').casefold())
            if not info: raise ValueError('谱面包缺少素材：' + n)
            return z.read(info)
        for info in infos:
            if not info.filename.lower().endswith(('.osu', '.mc')): continue
            if info.file_size > 4*1024**2: raise ValueError('osu 文件过大')
            original = z.read(info)
            extra = {}
            if info.filename.lower().endswith('.mc'):
                from .malody import convert_chart
                try:
                    t, extra = convert_chart(original)
                except (ValueError, KeyError, TypeError) as exc:
                    warnings.append(f'{info.filename}：{exc}，已跳过此难度')
                    continue
            else:
                t = original.decode('utf-8-sig', errors='replace')
            values = dict(re.findall(r'^([A-Za-z]+)[ \t]*:[ \t]*(.*?)[ \t\r]*$', t, re.M))
            if values.get('Mode', '0') != '3': continue
            bid = f'local-{token}-{len(result)}'
            base = str(PurePosixPath(info.filename.replace(chr(92), '/')).parent)
            base = '' if base == '.' else base + '/'
            audio = values.get('AudioFilename', '')
            label = values.get('Version', '') or info.filename
            if not audio and require_audio:
                warnings.append(f'{label}：谱面缺少音频名称，已跳过此难度')
                continue
            audio_path = base + audio
            if audio_path.replace(chr(92), '/').casefold() not in names and require_audio:
                warnings.append(f'{label}：缺少音频文件 {audio}，已跳过此难度')
                continue
            if not require_audio and (not audio or audio_path.replace(chr(92), '/').casefold() not in names):
                audio = ''
            bg = ''
            for line in t.splitlines():
                if line.strip().startswith('0,0,'):
                    bg = next(csv.reader([line]))[2]; break
            if bg and (base + bg).replace(chr(92), '/').casefold() not in names:
                warnings.append(f'{label}：缺少背景文件 {bg}，渲染时使用无背景模式')
                bg = ''
            assets = {}
            for name in [audio, bg]:
                if not name: continue
                body = read(base + name)
                safe = hashlib.sha256(body).hexdigest() + PurePosixPath(name).suffix.lower()
                (ROOT / safe).write_bytes(body); assets[name] = safe
            osu_name = bid + '.osu'
            (ROOT / osu_name).write_text(t, encoding='utf-8'); assets['map.osu'] = osu_name
            meta = {'beatmap_id':bid, 'beatmapset_id':bid, 'title':values.get('Title',''),
                    'version':values.get('Version',''), 'creator':values.get('Creator',''),
                    'keys':int(float(values.get('CircleSize','4'))), 'background_filename':bg,
                    'audio_filename':audio, 'chart_md5':hashlib.md5(original).hexdigest(), **extra}
            (ROOT / (bid + '.json')).write_text(json.dumps({'meta':meta,'assets':assets},ensure_ascii=False),encoding='utf-8')
            result.append(meta)
    if not result:
        if warnings:
            raise ValueError('没有可渲染的 osu!mania 难度；' + '；'.join(warnings))
        raise ValueError('包内没有 osu!mania 难度')
    return result, warnings
