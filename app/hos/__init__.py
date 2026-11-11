from flask import Blueprint

bp = Blueprint("hos", __name__, url_prefix="/hours")

from . import routes  # noqa: E402, F401
