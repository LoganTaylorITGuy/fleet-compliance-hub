from flask import Blueprint

bp = Blueprint("drivers", __name__, url_prefix="/drivers")

from . import routes  # noqa: E402, F401
