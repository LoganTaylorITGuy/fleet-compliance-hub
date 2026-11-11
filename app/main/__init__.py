"""Core pages that don't belong to a feature area (home, health check)."""

from flask import Blueprint

bp = Blueprint("main", __name__)

from . import routes  # noqa: E402, F401  (routes register themselves on bp)
