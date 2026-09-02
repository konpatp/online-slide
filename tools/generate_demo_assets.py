#!/usr/bin/env python3
"""Generate the public synthetic gallery assets deterministically."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "assets" / "gallery"
PALETTES = [
    ("#dce8ff", "#2f6fed", "#173e8c"),
    ("#ddf5ed", "#0f9d78", "#075e49"),
    ("#f4e6ff", "#8458c7", "#503078"),
]
VARIANTS = [0.76, 0.88, 1.00, 1.12, 1.24]


def svg(row: int, column: int) -> str:
    pale, mid, dark = PALETTES[row]
    scale = VARIANTS[column]
    radius = 37 + column * 3
    tilt = -18 + column * 9
    offset = row * 8 - 8
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 170" role="img">
  <rect width="240" height="170" rx="18" fill="#f8fafc"/>
  <path d="M18 134 C64 {72-offset}, 112 {150-offset}, 222 40" fill="none" stroke="{pale}" stroke-width="18" stroke-linecap="round"/>
  <g transform="translate(120 84) rotate({tilt}) scale({scale})">
    <rect x="-{radius}" y="-{radius}" width="{radius*2}" height="{radius*2}" rx="18" fill="{mid}" opacity=".93"/>
    <circle cx="{-radius//3}" cy="{-radius//4}" r="{max(7, radius//5)}" fill="white" opacity=".82"/>
    <path d="M-{radius//2} {radius//3} Q0 {-radius//5} {radius//2} {radius//3}" fill="none" stroke="{dark}" stroke-width="7" stroke-linecap="round"/>
  </g>
  <circle cx="28" cy="26" r="7" fill="{dark}" opacity=".32"/>
  <circle cx="210" cy="142" r="12" fill="{mid}" opacity=".18"/>
</svg>
'''


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for row in range(3):
        for column, suffix in enumerate("abcde"):
            path = OUT / f"{row + 1:02d}-{suffix}.svg"
            path.write_text(svg(row, column), encoding="utf-8")


if __name__ == "__main__":
    main()
