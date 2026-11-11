from __future__ import annotations

from datetime import datetime

from flask import abort, current_app, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy import select

from ..extensions import db
from ..formatting import LOCAL_TZ
from ..forms import ActionForm
from ..models import AuditLog
from ..permissions import can_edit, require_edit, require_view
from ..views import tenant_required
from . import bp
from .motive import MotiveNotConfigured
from .sync import get_connection, sync_motive


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


@bp.get("/")
@require_view("integrations")
@tenant_required
def index():
    connection = get_connection()
    db.session.commit()
    history = db.session.scalars(
        select(AuditLog).where(AuditLog.action == "sync").order_by(AuditLog.id.desc()).limit(5)
    ).all()
    demo = current_app.config["DEMO_MODE"]
    has_key = bool(current_app.config["MOTIVE_API_KEY"])
    return render_template(
        "integrations/index.html",
        connection=connection,
        history=history,
        demo=demo,
        has_key=has_key,
        connected=demo or has_key,
        action_form=ActionForm() if can_edit(current_user, "integrations") else None,
    )


@bp.post("/motive/sync")
@require_edit("integrations")
@tenant_required
def motive_sync():
    if not ActionForm().validate_on_submit():
        abort(400)
    try:
        result = sync_motive(local_now())
    except (MotiveNotConfigured, NotImplementedError) as exc:
        db.session.rollback()
        flash(f"Sync didn't run: {exc}", "error")
        return redirect(url_for("integrations.index"))
    flash(result.summary() + ".", "success")
    return redirect(url_for("integrations.index"))
