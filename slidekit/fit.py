"""Fast headline-fit estimate, calibrated against the browser renderer.

A full render takes ~20 s; authors otherwise discover a two-line headline by
rendering again and again. This module predicts the wrap in milliseconds from
the renderer's own inputs: the ``.slide-title``/``.recipe-header`` rules in
``public/styles.css`` (size, width, letter spacing, weight) and the font file
fontconfig resolves for the theme's font stack, the same file Chromium uses on
this host. It is an estimate for that renderer (another device with other
installed fonts may wrap differently); ``tools/browser_text_fit.py`` proves
agreement with real Chromium line boxes, so a stylesheet change that this
model does not follow fails a check instead of drifting silently.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import subprocess

STYLES = Path(__file__).resolve().parents[1] / "public" / "styles.css"
# Break opportunities Chromium uses inside headline prose: spaces, and after
# hyphens/dashes (an em dash also allows a break before it).
_TOKEN = re.compile(r"[^\s\-–—]*[\-–]|—|[^\s\-–—]+|\s+")


def _rule(css: str, selector: str) -> dict[str, str]:
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    if not match:
        raise ValueError(f"styles.css has no top-level {selector} rule")
    return {key.strip(): value.strip() for key, value in
            (item.split(":", 1) for item in match.group(1).split(";") if ":" in item)}


def _number(value: str, unit: str) -> float:
    match = re.search(r"(-?\d*\.?\d+)" + re.escape(unit), value)
    if not match:
        raise ValueError(f"expected a {unit} value, got {value!r}")
    return float(match.group(1))


@lru_cache(maxsize=4)
def headline_metrics(styles: Path = STYLES) -> dict:
    css = styles.read_text(encoding="utf-8")
    canvas = _number(_rule(css, ".slide-canvas")["width"], "px")
    header = _rule(css, ".recipe-header")
    title = _rule(css, ".slide-title")
    root = _rule(css, ":root")
    inner = canvas * (1 - (_number(header["left"], "%") + _number(header["right"], "%")) / 100)
    weight = int(title.get("font-weight", "400"))
    return {
        "font_px": canvas * _number(title["font-size"], "cqw") / 100,
        "max_width_px": inner * _number(title["max-width"], "%") / 100,
        "letter_spacing_em": _number(title.get("letter-spacing", "0em"), "em"),
        "line_height": float(title.get("line-height", "1.2")),
        "font_file": resolve_font(root["font-family"], weight), "weight": weight,
    }


GENERIC = {"serif", "sans-serif", "monospace", "system-ui", "ui-sans-serif", "ui-serif",
           "-apple-system", "blinkmacsystemfont", "cursive", "fantasy"}


def resolve_font(families: str, weight: int) -> str:
    """The font file Chromium on this host uses for a CSS family stack.

    Like the browser, take the first installed named family, else the system
    sans-serif; fontconfig's own weight scale (bold = 200) picks the face.
    """
    fc_weight = 200 if weight >= 600 else 80

    def match(family: str) -> tuple[str, str]:
        found = subprocess.run(["fc-match", "-f", "%{family}|%{file}", f"{family}:weight={fc_weight}"],
                               capture_output=True, text=True, timeout=10, check=True).stdout
        names, _, file = found.partition("|")
        return names, file.strip()

    for family in (item.strip().strip('"\'') for item in families.split(",")):
        if not family or family.lower() in GENERIC:
            continue
        names, file = match(family)
        if family.lower() in (name.strip().lower() for name in names.split(",")):
            return file
    return match("sans-serif")[1]


@lru_cache(maxsize=8)
def _font(path: str, size: float):
    from PIL import ImageFont
    return ImageFont.truetype(path, size=size)


def headline_fit(text: str, *, scale: float = 1.0, styles: Path = STYLES) -> dict:
    """Predicted line count and one-line capacity for a slide headline."""
    metrics = headline_metrics(styles)
    size = metrics["font_px"] * scale
    font = _font(metrics["font_file"], size)
    spacing = metrics["letter_spacing_em"] * size
    limit = metrics["max_width_px"]

    def width(value: str) -> float:
        return font.getlength(value) + spacing * len(value)

    lines = 0
    for paragraph in text.split("\n"):
        lines += 1
        current = ""
        for token in _TOKEN.findall(paragraph):
            trial = current + token
            if current.strip() and not token.isspace() and width(trial.rstrip()) > limit:
                lines += 1
                current = token
            else:
                current = trial
    flat = " ".join(text.split())
    per_char = width(flat) / max(1, len(flat))
    return {
        "lines": lines,
        "font_px": round(size, 1),
        "width_px": round(width(flat), 1),
        "max_width_px": round(limit, 1),
        "chars_per_line": int(limit // per_char) if per_char else 0,
        "renderer": f"Chromium with {Path(metrics['font_file']).stem} (estimate)",
    }


def describe(fit: dict) -> str:
    return (f"{fit['lines']} line{'s' if fit['lines'] != 1 else ''} at {fit['font_px']:g} px; "
            f"≤ ~{fit['chars_per_line']} characters fit on one line ({fit['renderer']})")
