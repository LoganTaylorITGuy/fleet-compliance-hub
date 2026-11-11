"""Template lint: Jinja expressions inside class="..." must be separated by spaces.

`py-2{{ extra }}` renders as `py-2hidden`, a class that doesn't exist, and the
mistake is invisible in code review. This caught a real bug: status badges lost
their background color and responsive table headers stopped hiding on phones.
"""

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"
CLASS_ATTR = re.compile(r'class="([^"]*)"')
# A class character glued to an opening tag, or a closing tag glued to one.
# A trailing "-" is allowed: progress-{{ n }} builds a class name on purpose.
GLUED_OPEN = re.compile(r"[A-Za-z0-9\]\)/]\{[{%]")
GLUED_CLOSE = re.compile(r"[}%]\}[A-Za-z0-9\[]")


def test_jinja_in_class_attributes_is_space_separated():
    problems = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for attr in CLASS_ATTR.findall(line):
                if GLUED_OPEN.search(attr) or GLUED_CLOSE.search(attr):
                    problems.append(f"{path.relative_to(TEMPLATES)}:{number}: {attr[:90]}")
    assert problems == [], "Add a space around the Jinja expression:\n" + "\n".join(problems)
