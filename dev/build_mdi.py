"""Builds slimdash/app/mdi.txt.gz from the npm package @mdi/svg (Pictogrammers, Apache 2.0).

    python dev/build_mdi.py <"package" folder extracted from svg-x.y.z.tgz>

One line per icon: "name<TAB>SVG path"; aliases: "alias<TAB>=name".
"""
import gzip
import json
import os
import re
import sys

src = sys.argv[1]
HERE = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(HERE, "..", "slimdash", "app", "mdi.txt.gz")
D = re.compile(r'<path d="([^"]+)"')

meta = json.load(open(os.path.join(src, "meta.json"), encoding="utf-8"))
lines, n = [], 0
for m in meta:
    name = m["name"]
    f = os.path.join(src, "svg", name + ".svg")
    if not os.path.exists(f):
        continue
    paths = D.findall(open(f, encoding="utf-8").read())
    if not paths:
        continue
    lines.append("%s\t%s" % (name, " ".join(paths)))
    n += 1
    for a in m.get("aliases") or []:
        lines.append("%s\t=%s" % (a, name))
with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as g:
    g.write("\n".join(lines) + "\n")
print("%d icons, %d lines, %d bytes" % (n, len(lines), os.path.getsize(out)))
