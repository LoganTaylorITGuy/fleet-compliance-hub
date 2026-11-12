"""The Audit log page: filterable history of who changed what.

Admins see it; Carrier Viewers never do (see ADMIN_ONLY_VIEW in permissions.py).
"""

from __future__ import annotations

from contextlib import nullcontext

from flask import render_template, request
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import AuditLog, Role, Tenant, User
from ..permissions import require_view
from ..tenancy import all_tenants
from . import bp

PAGE_SIZE = 50


@bp.get("/")
@require_view("audit")
def index():
    """Provider Admins see every tenant; Carrier Admins see only their own."""
    is_provider_admin = current_user.role == Role.PROVIDER_ADMIN
    filters = {
        "action": request.args.get("action", "").strip(),
        "table": request.args.get("table", "").strip(),
        "user_id": request.args.get("user_id", type=int),
        "tenant_id": request.args.get("tenant_id", type=int) if is_provider_admin else None,
    }
    page = max(request.args.get("page", 1, type=int), 1)

    stmt = select(AuditLog).options(selectinload(AuditLog.user)).order_by(AuditLog.id.desc())
    if filters["action"]:
        stmt = stmt.where(AuditLog.action == filters["action"])
    if filters["table"]:
        stmt = stmt.where(AuditLog.table_name == filters["table"])
    if filters["user_id"]:
        stmt = stmt.where(AuditLog.user_id == filters["user_id"])
    if filters["tenant_id"]:
        stmt = stmt.where(AuditLog.tenant_id == filters["tenant_id"])

    # Provider Admins read across tenants; everyone else stays in their scope.
    with all_tenants() if is_provider_admin else nullcontext():
        entries = db.session.scalars(stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE + 1)).all()
        actions = db.session.scalars(select(AuditLog.action).distinct().order_by("action")).all()
        tables = db.session.scalars(
            select(AuditLog.table_name)
            .where(AuditLog.table_name.is_not(None))
            .distinct()
            .order_by("table_name")
        ).all()

    tenants = (
        {
            t.id: t
            for t in db.session.scalars(
                select(Tenant).where(Tenant.provider_id == current_user.provider_id)
            )
        }
        if is_provider_admin
        else {}
    )
    users = _users_for_filter(is_provider_admin)
    return render_template(
        "audit/index.html",
        entries=entries[:PAGE_SIZE],
        has_next=len(entries) > PAGE_SIZE,
        page=page,
        filters=filters,
        actions=actions,
        tables=tables,
        tenants=tenants,
        users=users,
        show_tenant=is_provider_admin,
    )


def _users_for_filter(is_provider_admin: bool) -> list[User]:
    """Users to offer in the filter dropdown, limited to the viewer's own world."""
    stmt = select(User).order_by(User.name)
    if is_provider_admin:
        stmt = stmt.where(
            (User.provider_id == current_user.provider_id)
            | User.tenant_id.in_(
                select(Tenant.id).where(Tenant.provider_id == current_user.provider_id)
            )
        )
    else:
        stmt = stmt.where(User.tenant_id == current_user.tenant_id)
    return list(db.session.scalars(stmt))
