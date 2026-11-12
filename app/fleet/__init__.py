"""Fleet: tractors and trailers, DVIRs, maintenance and repairs."""

from flask import Blueprint

bp = Blueprint("fleet", __name__, url_prefix="/fleet")

from . import routes  # noqa: E402, F401
