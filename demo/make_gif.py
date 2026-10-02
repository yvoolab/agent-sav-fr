#!/usr/bin/env python3
"""Rend demo/demo.gif à partir de sorties réelles de l'agent (demo/exemple-*.txt).
Les textes sont capturés tels quels : python3 agent.py --exemple N > demo/exemple-N.txt
Requiert Pillow (seul outil hors stdlib du dépôt, et seulement pour la démo)."""
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
W, COLS, ROWS, LH, PAD = 1100, 100, 30, 22, 24
BG, FG, DIM, ACC, TOOL = "#2B2725", "#F5EFE6", "#9C948C", "#C9584F", "#D9C7A7"
FONT = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)

def lines_of(path):
    out = []
    for raw in path.read_text(encoding="utf-8").rstrip().splitlines():
        out += textwrap.wrap(raw, COLS, subsequent_indent="    ") or [""]
    return out

def color(line):
    s = line.strip()
    if s.startswith(("→", "←")): return TOOL
    if s.startswith("ACTION"): return ACC
    if s.startswith(("De :", "Objet :", "─", "BROUILLON")): return DIM
    return FG

def frame(shown, title):
    img = Image.new("RGB", (W, PAD * 2 + LH * (ROWS + 1)), BG)
    d = ImageDraw.Draw(img)
    d.text((PAD, PAD), title, font=FONT, fill=DIM)
    for i, l in enumerate(shown[-ROWS:]):
        d.text((PAD, PAD + LH * (i + 1)), l, font=FONT, fill=color(l))
    return img

frames, durations = [], []
for n in ("04", "13"):
    title = f"$ python3 agent.py --exemple {int(n)}"
    lines = lines_of(HERE / f"exemple-{n}.txt")
    for k in range(1, len(lines) + 1):
        frames.append(frame(lines[:k], title))
        l = lines[k - 1].strip()
        durations.append(900 if l.startswith(("→", "←", "ACTION")) else 90)
    durations[-1] = 5000
frames[0].save(HERE / "demo.gif", save_all=True, append_images=frames[1:],
               duration=durations, loop=0, optimize=True)
print(f"{len(frames)} images · {sum(durations)/1000:.0f} s")
