from flask import jsonify, render_template

from . import bp


@bp.get("/")
def index():
    """Landing page. Replaced by the role-aware dashboard in a later step."""
    return render_template("main/index.html")


@bp.get("/healthz")
def healthz():
    """Liveness check for staging and production hosting."""
    return jsonify(status="ok")
