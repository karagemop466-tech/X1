"""Build entry point: render the static site from the collected datasets.

Usage::

    python -m nflx.build_site --data data/nfl --out _site
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Dict, List

from .analysis import build_correlation, build_depth
from .build import BuildContext
from .pages import PAGES

CSS_SOURCE = Path(__file__).resolve().parents[2] / "assets" / "site.css"


def build(data_dir: Path, out_dir: Path, *, clean: bool = True) -> Dict[str, int]:
    """Render every page into ``out_dir``."""
    # Derived datasets first: the pages read them.
    build_depth(data_dir, data_dir)
    build_correlation(data_dir, data_dir)

    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ctx = BuildContext(data_dir)
    written = 0
    for relative, renderer in PAGES.items():
        target = out_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        html = renderer(ctx)
        target.write_text(html, encoding="utf-8")
        written += 1
        print(f"  wrote {target} ({len(html)} bytes)")

    # Copy the stylesheet.
    assets = out_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    if CSS_SOURCE.exists():
        shutil.copy2(CSS_SOURCE, assets / "site.css")
        print(f"  copied {CSS_SOURCE} -> {assets / 'site.css'}")
    else:
        print(f"  ! stylesheet not found at {CSS_SOURCE}")

    # Publish the raw datasets so every number on the site can be checked.
    data_out = out_dir / "data"
    data_out.mkdir(parents=True, exist_ok=True)
    for json_file in sorted(data_dir.glob("*.json")):
        shutil.copy2(json_file, data_out / json_file.name)
        print(f"  copied {json_file} -> {data_out / json_file.name}")

    print(f"built {written} pages into {out_dir}")
    return {"pages": written}


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the static dashboard.")
    parser.add_argument("--data", default="data/nfl")
    parser.add_argument("--out", default="_site")
    parser.add_argument("--no-clean", action="store_true")
    args = parser.parse_args(argv)

    data_dir = Path(args.data)
    if not data_dir.exists():
        print(f"data directory not found: {data_dir}", file=sys.stderr)
        return 2
    build(data_dir, Path(args.out), clean=not args.no_clean)
    return 0


if __name__ == "__main__":
    sys.exit(main())
