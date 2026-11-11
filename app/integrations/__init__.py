"""Outside systems: the Motive ELD stub, the sync job, and the Integrations page."""

from flask import Blueprint

bp = Blueprint("integrations", __name__, url_prefix="/integrations")

from . import routes  # noqa: E402, F401
