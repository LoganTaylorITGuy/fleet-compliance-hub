"""Provider dashboard (all carriers) and carrier dashboard (one carrier)."""

from flask import Blueprint

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

from . import routes  # noqa: E402, F401
