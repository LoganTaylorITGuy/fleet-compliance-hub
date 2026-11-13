"""Printed audit packets always use the light theme's colors.

input.css pins the color tokens inside ``@media print`` so a packet printed
from dark mode isn't light text on white paper. This keeps those pinned values
equal to the light theme in :root, so changing a token can't leave print behind.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app/static/css"
CSS = (STATIC / "input.css").read_text()


def _tokens(block: str) -> dict[str, str]:
    return {
        k: v.strip() for k, v in re.findall(r"--([\w-]+):\s*([^;!]+?)\s*(?:!important)?;", block)
    }


def _light() -> dict[str, str]:
    match = re.search(r"^:root\s*\{(.*?)\n\}", CSS, re.S | re.M)
    assert match
    return _tokens(match.group(1))


def _print() -> dict[str, str]:
    match = re.search(r"@media print\s*\{\s*:root\s*\{(.*?)\n\s*\}", CSS, re.S)
    assert match, "input.css has no @media print :root block"
    return _tokens(match.group(1))


def test_print_tokens_match_the_light_theme():
    light, printed = _light(), _print()
    assert printed, "no tokens pinned for print"
    mismatched = {k: (v, light.get(k)) for k, v in printed.items() if light.get(k) != v}
    assert mismatched == {}, f"print token != light token: {mismatched}"


def test_every_color_the_packet_uses_is_pinned_for_print():
    # Text, rules and the status badge colors. Glass tokens don't matter on paper.
    needed = {"ink", "muted", "line", "line-strong", "danger-ink", "warn-ink", "ok-ink"}
    needed |= {f"{s}-{p}" for s in ("danger", "warn", "ok") for p in ("soft", "line")}
    assert needed <= set(_print())


def test_compiled_css_includes_the_print_rules():
    assert "@media print" in (STATIC / "app.css").read_text(), "run: npm run build:css"
