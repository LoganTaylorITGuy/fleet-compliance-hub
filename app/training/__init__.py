"""Training records and driving academy student progress."""

from flask import Blueprint

bp = Blueprint("training", __name__, url_prefix="/training")

from . import routes  # noqa: E402, F401
