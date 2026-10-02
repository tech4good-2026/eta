#!/usr/bin/env python3
"""Check README links and screen/diagram assets without network access."""
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree
import re
import struct

root = Path(__file__).resolve().parents[1]
readme = root / 'README.md'
text = readme.read_text(encoding='utf-8')
errors = []
references = re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', text)
references += re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', text)
checked = 0
for reference in references:
    url = urlsplit(reference.strip('<>'))
    if url.scheme or reference.startswith('#'):
        continue
    path = (root / unquote(url.path)).resolve()
    if not path.is_relative_to(root):
        errors.append(f'Link leaves repository: {reference}')
    elif not path.is_file():
        errors.append(f'Missing file: {reference}')
    checked += 1

for path in (root / 'docs/assets/screens').glob('demo-*.png'):
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        errors.append(f'Invalid PNG: {path.name}')
        continue
    width, height = struct.unpack('>II', data[16:24])
    if min(width, height) < 300:
        errors.append(f'Unreadable screen size: {path.name} {width}x{height}')

svg = root / 'docs/assets/architecture/request-flow.svg'
try:
    tree = ElementTree.parse(svg)
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    for name in ('title', 'desc'):
        element = tree.find(f'svg:{name}', ns)
        if element is None or not element.text:
            errors.append(f'Diagram needs accessible {name}')
except (OSError, ElementTree.ParseError) as error:
    errors.append(str(error))

for match in re.finditer(r'!\[([^\]]*)\]\(', text):
    if not match.group(1).strip():
        errors.append('Image has empty alt text')
if errors:
    raise SystemExit('\n'.join(errors))
print(f'README: {checked} local links, screenshots and SVG source verified')
