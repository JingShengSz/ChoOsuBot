"""Package native Photoshop cutouts and vector masks without recoloring pixels."""
from pathlib import Path
import base64
import json
import io
import re
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
for n in range(1, 11):
    source = HERE / 'reform_sources' / f'reform{n}.png'
    # Published SVGs embed the original crop, so reconstruction also works
    # without the ignored local Photoshop working files.
    if source.is_file():
        source_pixels=source.read_bytes()
    else:
        embedded=re.search(r'base64,([^"\s]+)',(HERE/f'reform{n}.svg').read_text(encoding='utf-8'))
        source_pixels=base64.b64decode(embedded.group(1))
    with Image.open(io.BytesIO(source_pixels)) as im:
        width, height = im.size
        alpha = np.asarray(im.getchannel('A'))
    mask = ''
    if n in (6, 8):
        # An enclosed transparent counter defines the digit's inner contour.
        # The convex vector contour bridges letters mistakenly kept by Select Subject.
        seed = (220, 430) if n == 6 else (220, 170)
        stack = [seed]
        points = set()
        while stack:
            x, y = stack.pop()
            if (x, y) in points or not (0 <= x < width and 0 <= y < height) or alpha[y, x] > 8:
                continue
            points.add((x, y))
            stack.extend(((x-1,y),(x+1,y),(x,y-1),(x,y+1)))
        if not points or any(x in (0,width-1) or y in (0,height-1) for x,y in points):
            raise ValueError(f'Reform {n}: inner counter is not enclosed')
        def cross(o, a, b):
            return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
        lower, upper = [], []
        for point in sorted(points):
            while len(lower) > 1 and cross(lower[-2],lower[-1],point) <= 0:
                lower.pop()
            lower.append(point)
        for point in sorted(points,reverse=True):
            while len(upper) > 1 and cross(upper[-2],upper[-1],point) <= 0:
                upper.pop()
            upper.append(point)
        hull = lower[:-1] + upper[:-1]
        polygon = ' '.join(f'{x},{y}' for x,y in hull)
        fringe = '<rect x="398" y="348" width="20" height="100" fill="black"/>' if n == 6 else ''
        counter = ( '<path d="M220 309 C179 309 153 334 136 367 C124 393 127 439 149 480 C166 519 189 536 218 533 C258 535 281 501 286 439 C291 387 286 347 259 324 C247 313 235 309 220 309Z" fill="black"/>'
                    if n == 6 else f'<polygon points="{polygon}" fill="black" stroke="black" stroke-width="6" stroke-linejoin="round"/>')
        mask = f'<defs><mask id="counter" maskUnits="userSpaceOnUse" x="0" y="0" width="{width}" height="{height}"><rect width="{width}" height="{height}" fill="white"/>{counter}{fringe}</mask></defs>'
        (HERE / f'reform{n}_mask.json').write_text(json.dumps(hull),encoding='utf-8')
    pixels = base64.b64encode(source_pixels).decode('ascii')
    x, y = (1920-width)//2, (1080-height)//2
    masking = ' mask="url(#counter)"' if mask else ''
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080"><g transform="translate({x} {y})">{mask}<image width="{width}" height="{height}" href="data:image/png;base64,{pixels}"{masking}/></g></svg>'
    (HERE / f'reform{n}.svg').write_text(svg,encoding='utf-8')
print('Prepared 10 source-preserving SVG icons; refined counters in 6 and 8')
