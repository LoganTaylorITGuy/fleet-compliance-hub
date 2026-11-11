"""WCAG 2.1 AA contrast for the design tokens, in light and dark themes.

Glass is translucent, so text sits on a blend of the panel color and whatever
is behind it. These tests composite each glass surface over the strongest
backdrop glow (the worst case for contrast) and check every text/background
pair the templates use against 4.5:1 (normal text). Values are read straight
from app/static/css/input.css, so changing a token re-runs the check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parent.parent / "app/static/css/input.css").read_text()
AA = 4.5


def _block(selector_pattern: str) -> dict[str, str]:
    match = re.search(selector_pattern + r"\s*\{(.*?)\n\s*\}", CSS, re.S | re.M)
    assert match, selector_pattern
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", match.group(1)))


LIGHT = _block(r"^:root")
DARK = {**LIGHT, **_block(r":root\[data-theme=\"dark\"\]")}
DARK_MEDIA = {**LIGHT, **_block(r":root:not\(\[data-theme=\"light\"\]\)")}


def rgb(theme: dict, name: str) -> tuple[float, float, float]:
    return tuple(float(v) for v in theme[name].split())


def blend(top, alpha: float, bottom):
    return tuple(t * alpha + b * (1 - alpha) for t, b in zip(top, bottom, strict=True))


def luminance(color) -> float:
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def backdrops(theme: dict):
    """The canvas alone and under each glow at full strength."""
    canvas = rgb(theme, "canvas")
    alpha = float(theme["glow-alpha"])
    return [canvas] + [blend(rgb(theme, f"glow-{n}"), alpha, canvas) for n in (1, 2, 3)]


def glass_surfaces(theme: dict):
    glass, alpha = rgb(theme, "glass"), float(theme["glass-alpha"])
    surfaces = [blend(glass, alpha, back) for back in backdrops(theme)]
    surfaces.append(rgb(theme, "glass-solid"))  # reduced-transparency fallback
    return surfaces


THEMES = {"light": LIGHT, "dark": DARK, "dark (system)": DARK_MEDIA}


def test_explicit_dark_matches_system_dark():
    """The two dark blocks must stay identical, or the switcher and OS disagree."""
    assert _block(r":root\[data-theme=\"dark\"\]") == _block(
        r":root:not\(\[data-theme=\"light\"\]\)"
    )


@pytest.mark.parametrize("theme_name", THEMES)
@pytest.mark.parametrize("token", ["ink", "muted", "subtle", "link", "link-strong"])
def test_text_on_glass(theme_name, token):
    theme = THEMES[theme_name]
    worst = min(contrast(rgb(theme, token), s) for s in glass_surfaces(theme))
    assert worst >= AA, f"{token} on glass in {theme_name}: {worst:.2f}:1"


@pytest.mark.parametrize("theme_name", THEMES)
@pytest.mark.parametrize("tone", ["danger", "warn", "ok", "info"])
def test_status_badges(theme_name, tone):
    theme = THEMES[theme_name]
    ink, soft = rgb(theme, f"{tone}-ink"), rgb(theme, f"{tone}-soft")
    # Badges use the soft color at full strength; section headers use it at 70% over glass.
    surfaces = [soft] + [blend(soft, 0.7, g) for g in glass_surfaces(theme)]
    worst = min(contrast(ink, s) for s in surfaces)
    assert worst >= AA, f"{tone} badge in {theme_name}: {worst:.2f}:1"


@pytest.mark.parametrize("theme_name", THEMES)
def test_buttons(theme_name):
    theme = THEMES[theme_name]
    white = rgb(theme, "on-accent")
    assert contrast(white, rgb(theme, "accent")) >= AA
    assert contrast(white, rgb(theme, "accent-strong")) >= AA
    assert contrast((255, 255, 255), rgb(theme, "ok-solid")) >= AA


@pytest.mark.parametrize("theme_name", THEMES)
def test_active_nav_and_avatar(theme_name):
    """link-strong on the accent/15 tint used for the current page and avatar."""
    theme = THEMES[theme_name]
    worst = min(
        contrast(rgb(theme, "link-strong"), blend(rgb(theme, "accent"), 0.15, s))
        for s in glass_surfaces(theme)
    )
    assert worst >= AA, f"{theme_name}: {worst:.2f}:1"
