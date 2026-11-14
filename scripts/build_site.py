#!/usr/bin/env python3
"""Assemble only the public static site files into _site/ for GitHub Pages."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir()
for name in ("index.html", "COORDINATION.md"):
    shutil.copy2(ROOT / name, OUT / name)
for name in ("assets", "pages"):
    shutil.copytree(ROOT / name, OUT / name)
print(f"Built Pages artifact at {OUT} ({sum(1 for p in OUT.rglob('*') if p.is_file())} files).")
