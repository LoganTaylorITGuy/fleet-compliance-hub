from flask import Blueprint

bp = Blueprint("fleet", __name__, url_prefix="/fleet")

from . import routes  # noqa: E402, F401
