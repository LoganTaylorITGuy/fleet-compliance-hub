"""Login, logout, demo role switcher, and the per-request tenant scope."""

from flask import Blueprint

bp = Blueprint("auth", __name__)

from . import routes  # noqa: E402, F401
