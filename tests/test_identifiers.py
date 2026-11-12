"""The shared matching rule for CDL numbers, unit numbers and VINs."""

import pytest

from app.identifiers import normalize_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TR501", "TR501"),
        ("tr-501", "TR501"),
        (" tr 501 ", "TR501"),
        ("99-123 456", "99123456"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_key(raw, expected):
    assert normalize_key(raw) == expected
