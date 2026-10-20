#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Symbole der Web-App (PNG 512/192/180) zeichnen – dunkle Kachel mit vier Dashboard-Feldern
in Cyan, passend zu den Lerndashboards. Aufruf: /usr/bin/python3 werkzeuge/symbole.py"""
from pathlib import Path
from PIL import Image, ImageDraw

ZIEL = Path(__file__).resolve().parent.parent / "docs" / "icons"
ZIEL.mkdir(parents=True, exist_ok=True)

G = 1024                                     # groß zeichnen, dann verkleinern (glatte Kanten)
img = Image.new("RGBA", (G, G), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((0, 0, G - 1, G - 1), radius=int(G * 0.22), fill=(11, 16, 32, 255))
# feiner Rand innen
d.rounded_rectangle((18, 18, G - 19, G - 19), radius=int(G * 0.2), outline=(31, 39, 56, 255), width=6)

# vier Felder wie Stunden-Kacheln; eines leuchtet (nächste Stunde)
rand, luecke = 190, 44
w = (G - 2 * rand - luecke) // 2
felder = [(rand, rand), (rand + w + luecke, rand), (rand, rand + w + luecke), (rand + w + luecke, rand + w + luecke)]
for i, (x, y) in enumerate(felder):
    if i == 0:
        d.rounded_rectangle((x, y, x + w, y + w), radius=54, fill=(22, 197, 232, 255))
        # kleines Signal (Rechteckimpuls) im leuchtenden Feld
        p = [(x + 48, y + w - 90), (x + w // 2 - 30, y + w - 90), (x + w // 2 - 30, y + 90),
             (x + w // 2 + 60, y + 90), (x + w // 2 + 60, y + w - 90), (x + w - 48, y + w - 90)]
        d.line(p, fill=(11, 16, 32, 255), width=26, joint="curve")
    else:
        d.rounded_rectangle((x, y, x + w, y + w), radius=54, fill=(28, 38, 64, 255), outline=(22, 197, 232, 160), width=8)
        d.rounded_rectangle((x + 46, y + 56, x + w - 46, y + 96), radius=16, fill=(22, 197, 232, 110))
        d.rounded_rectangle((x + 46, y + 128, x + int(w * 0.62), y + 160), radius=14, fill=(110, 125, 160, 200))

for n in (512, 192, 180):
    img.resize((n, n), Image.LANCZOS).save(ZIEL / f"icon-{n}.png", optimize=True)
    print("geschrieben:", ZIEL / f"icon-{n}.png")
