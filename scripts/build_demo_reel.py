"""Stitch the tool screenshots into a scrolling docs/demo-reel.gif.

Build-only tool (not a runtime dependency). Reads the committed PNGs in
docs/screenshots/ in tool order and writes an animated GIF for the README.
Deterministic — no clock, no randomness — so the same screenshots always
produce the same bytes, which lets CI rebuild it and commit only a real change.

The source screenshots are full-page captures of very different heights. Rather
than crop them, each frame scrolls a fixed 16:10 viewport down the full page:
a dwell at the top, a scroll to the bottom, a dwell there, then the next tool.
Per-frame durations keep each dwell a single frame, so the GIF stays small.

    python scripts/build_demo_reel.py            # writes docs/demo-reel.gif
    python scripts/build_demo_reel.py --check     # exit 1 if the GIF is stale

Requires Pillow (`pip install pillow==11.3.0`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

# Tool order mirrors the README sections.
FRAME_ORDER = [
    "0-home-mapping",
    "1-forecast-narrative",
    "2-qbr-assembler",
    "3-account-plan",
]

ROOT = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = ROOT / "docs" / "screenshots"
OUTPUT = ROOT / "docs" / "demo-reel.gif"

FRAME_WIDTH = 900                       # px
FRAME_HEIGHT = FRAME_WIDTH * 10 // 16   # 16:10 viewport -> 562
COLORS = 128

TARGET_SCROLL_STEP = 95                 # px between scroll frames (tuned for size)
MAX_SCROLL_FRAMES = 14                  # cap per page, so long pages scroll faster
SCROLL_MS = 45                          # per scroll frame (~22fps)
DWELL_MS = 1100                         # single held frame at top and bottom of each page


def _viewport(page: Image.Image, y: int) -> Image.Image:
    crop = page.crop((0, y, FRAME_WIDTH, y + FRAME_HEIGHT))
    return crop.quantize(colors=COLORS, method=Image.MEDIANCUT, dither=Image.Dither.NONE)


def _page_frames(name: str) -> tuple[list[Image.Image], list[int]]:
    path = SCREENSHOT_DIR / f"{name}.png"
    if not path.exists():
        sys.exit(f"missing screenshot: {path.relative_to(ROOT)}")
    img = Image.open(path).convert("RGB")
    scaled_h = round(img.height * FRAME_WIDTH / img.width)
    page = img.resize((FRAME_WIDTH, scaled_h), Image.LANCZOS)

    distance = scaled_h - FRAME_HEIGHT
    if distance <= 0:                   # page shorter than the viewport: pad and hold
        canvas = Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), "white")
        canvas.paste(page, (0, 0))
        return [canvas.quantize(colors=COLORS, method=Image.MEDIANCUT, dither=Image.Dither.NONE)], [DWELL_MS]

    steps = min(MAX_SCROLL_FRAMES, max(1, round(distance / TARGET_SCROLL_STEP)))
    ys = [round(i * distance / steps) for i in range(steps + 1)]  # 0 .. distance inclusive
    frames = [_viewport(page, y) for y in ys]
    durations = [DWELL_MS] + [SCROLL_MS] * (len(frames) - 2) + [DWELL_MS]
    return frames, durations


def build(destination: Path) -> None:
    frames: list[Image.Image] = []
    durations: list[int] = []
    for name in FRAME_ORDER:
        f, d = _page_frames(name)
        frames += f
        durations += d
    frames[0].save(
        destination,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild to a temp path and fail if it differs from the committed GIF",
    )
    args = parser.parse_args()

    if args.check:
        tmp = OUTPUT.with_name("demo-reel.check.gif")
        build(tmp)
        stale = not OUTPUT.exists() or tmp.read_bytes() != OUTPUT.read_bytes()
        tmp.unlink(missing_ok=True)
        if stale:
            sys.exit(
                f"{OUTPUT.relative_to(ROOT)} is stale; run: python scripts/build_demo_reel.py"
            )
        print(f"{OUTPUT.relative_to(ROOT)} is up to date")
        return

    build(OUTPUT)
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
