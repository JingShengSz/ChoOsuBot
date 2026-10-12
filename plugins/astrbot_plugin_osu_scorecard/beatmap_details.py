"""Retrieve Detail Pro pages from the same render node used by OM."""
from io import BytesIO
from pathlib import Path
import zipfile
import aiohttp
import re
import math
import shlex


def detail_args(raw: str) -> tuple[str, float]:
    """Parse an optional map ID and one explicit prediction speed."""
    tokens=shlex.split(raw)
    bid=''; rate=1.0; specified=False; index=0
    while index<len(tokens):
        token=tokens[index].lower()
        if token in ('ht','-ht','+ht','dt','-dt','+dt'):
            value=.75 if token.lstrip('-+')=='ht' else 1.5
        elif token in ('-rate','--rate','-speed','--speed'):
            index+=1
            if index>=len(tokens): raise ValueError('倍速参数后需要数字，例如 4312004 1.2')
            value=float(tokens[index])
        elif token.startswith(('-rate=','--rate=','-speed=','--speed=')):
            value=float(token.split('=',1)[1])
        elif re.fullmatch(r'[1-9][0-9]{0,9}',token) and not bid:
            bid=token;index+=1;continue
        elif re.fullmatch(r'(?:\d+(?:\.\d*)?|\.\d+)',token):
            value=float(token)
        else:
            raise ValueError('用法：dtl/dtlp [谱面ID] [dt | ht | 1.2]；也可回复谱面文件')
        if specified: raise ValueError('HT、DT 和自定义倍速只能选择一个')
        if not math.isfinite(value) or not .1<=value<=3: raise ValueError('倍速范围为 0.1～3.0')
        rate=round(value,6);specified=True;index+=1
    return bid,rate

class BeatmapDetails:
    def __init__(self, cache: Path, server: str):
        self.cache = cache
        self.server = server.rstrip('/')

    async def pages(self, bid: int | str, *, speed_rate: float=1.0) -> list[Path]:
        if not re.fullmatch(r'(?:[1-9][0-9]{0,9}|local-[0-9a-f]{32}-[0-9]+)', str(bid)):
            raise ValueError('无效的谱面来源')
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            async with session.get(f'{self.server}/api/detail/{bid}',params={'rate':str(speed_rate)}) as response:
                if response.status != 200:
                    try:
                        error = (await response.json()).get('error') or '详情服务不可用'
                    except Exception:
                        error = '详情服务不可用'
                    raise RuntimeError(error)
                raw = await response.read()
        target = self.cache / str(bid) / f'rate-{speed_rate:g}'
        target.mkdir(parents=True, exist_ok=True)
        pages = []
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            for index in range(1,4):
                name = f'detail_{index}.png'
                body = archive.read(name)
                if not body.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise RuntimeError('详情服务未返回有效图片')
                path = target / name
                path.write_bytes(body)
                pages.append(path)
        return pages

    async def compact(self, bid: int | str, *, speed_rate: float=1.0) -> Path:
        if not re.fullmatch(r'(?:[1-9][0-9]{0,9}|local-[0-9a-f]{32}-[0-9]+)',str(bid)):
            raise ValueError('无效的谱面来源')
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            async with session.get(f'{self.server}/api/detail-compact/{bid}',params={'rate':str(speed_rate)}) as response:
                if response.status != 200:
                    try:
                        error = (await response.json()).get('error') or 'DTL 服务不可用'
                    except Exception:
                        error = 'DTL 服务不可用'
                    raise RuntimeError(error)
                raw = await response.read()
        if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError('DTL 服务未返回有效图片')
        target = self.cache / str(bid) / f'rate-{speed_rate:g}'
        target.mkdir(parents=True,exist_ok=True)
        image = target/'compact.png'
        image.write_bytes(raw)
        return image
