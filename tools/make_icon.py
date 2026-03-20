from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python tools/make_icon.py <input-png> <output-ico>")

    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve()

    if not src.exists():
        raise FileNotFoundError(src)

    dst.parent.mkdir(parents=True, exist_ok=True)

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    with Image.open(src) as img:
        rgba = img.convert("RGBA")
        rgba.save(dst, format="ICO", sizes=sizes)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

