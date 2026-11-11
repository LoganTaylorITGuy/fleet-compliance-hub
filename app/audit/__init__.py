"""Audit log: who changed what, and when.

Like tenant isolation, auditing happens in one place. An ``after_flush`` session
hook writes an AuditLog row for every insert, update and delete of tenant data,
with before/after values for the columns that changed. Views don't call it.

Bulk jobs (spreadsheet import, Motive sync) wrap their work in
``audit_suppressed()`` and write one summary entry with ``record()`` instead of
hundreds of row-level entries.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime
from decimal import Decimal

from flask import Blueprint, has_request_context
from flask_login import current_user
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from ..extensions import db
from ..models import AuditLog, utcnow
from ..tenancy import TenantScoped, current_scope

bp = Blueprint("audit", __name__, url_prefix="/audit")

IGNORED_COLUMNS = {"created_at", "updated_at"}

_suppressed: ContextVar[bool] = ContextVar("audit_suppressed", default=False)


@contextmanager
def audit_suppressed() -> Iterator[None]:
    token = _suppressed.set(True)
    try:
        yield
    finally:
        _suppressed.reset(token)


def current_user_id() -> int | None:
    if has_request_context() and current_user and current_user.is_authenticated:
        return current_user.id
    return None


def record(
    action: str,
    summary: str,
    *,
    table_name: str | None = None,
    record_id: int | None = None,
    tenant_id: int | None = None,
    user_id: int | None = None,
) -> None:
    """Add a summary audit entry (login, import, sync...) to the current session."""
    scope = current_scope()
    db.session.add(
        AuditLog(
            user_id=user_id if user_id is not None else current_user_id(),
            tenant_id=tenant_id if tenant_id is not None else scope.tenant_id,
            action=action,
            table_name=table_name,
            record_id=record_id,
            summary=summary[:300],
        )
    )


def _plain(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _snapshot(obj) -> dict:
    mapper = inspect(obj).mapper
    return {
        c.key: _plain(getattr(obj, c.key))
        for c in mapper.column_attrs
        if c.key not in IGNORED_COLUMNS
    }


def _changes(obj) -> tuple[dict, dict]:
    state = inspect(obj)
    before, after = {}, {}
    for attr in state.mapper.column_attrs:
        if attr.key in IGNORED_COLUMNS:
            continue
        history = state.attrs[attr.key].history
        if history.has_changes():
            before[attr.key] = _plain(history.deleted[0]) if history.deleted else None
            after[attr.key] = _plain(history.added[0]) if history.added else None
    return before, after


@event.listens_for(Session, "after_flush")
def _write_audit_rows(session: Session, _flush_context) -> None:
    if _suppressed.get():
        return
    rows = []
    user_id = current_user_id()
    now = utcnow()

    def add(obj, action: str, before: dict | None, after: dict | None) -> None:
        rows.append(
            {
                "user_id": user_id,
                "tenant_id": obj.tenant_id,
                "action": action,
                "table_name": obj.__tablename__,
                "record_id": obj.id,
                "before": before,
                "after": after,
                "created_at": now,
            }
        )

    for obj in session.new:
        if isinstance(obj, TenantScoped) and not isinstance(obj, AuditLog):
            add(obj, "create", None, _snapshot(obj))
    for obj in session.dirty:
        if isinstance(obj, TenantScoped) and not isinstance(obj, AuditLog):
            before, after = _changes(obj)
            if after:
                add(obj, "update", before, after)
    for obj in session.deleted:
        if isinstance(obj, TenantScoped) and not isinstance(obj, AuditLog):
            add(obj, "delete", _snapshot(obj), None)

    if rows:
        # Core insert on the flush's own connection: same transaction, and it
        # doesn't start a second ORM flush from inside this one.
        session.connection().execute(AuditLog.__table__.insert(), rows)


from . import routes  # noqa: E402, F401
