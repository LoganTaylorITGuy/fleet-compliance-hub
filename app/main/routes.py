"""Home redirect, favicon, and the /healthz check used by hosting."""

from flask import g, jsonify, redirect, url_for
from flask_login import current_user

from ..permissions import is_provider
from . import bp


@bp.get("/")
def index():
    """Send each user to the right starting page."""
    if is_provider(current_user) and g.get("active_tenant") is None:
        return redirect(url_for("dashboard.provider"))
    return redirect(url_for("dashboard.carrier"))


@bp.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.svg"), code=301)


@bp.get("/healthz")
def healthz():
    """Liveness check for staging and production hosting."""
    return jsonify(status="ok")
