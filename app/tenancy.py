"""Tenant isolation, enforced in one place.

Every model that holds carrier data inherits :class:`TenantScoped`. Two
SQLAlchemy session events, registered once at import time, then apply to every
query and every write in the app:

* ``do_orm_execute`` adds ``WHERE tenant_id = <current tenant>`` to every ORM
  SELECT, UPDATE and DELETE that touches a tenant-scoped table, including
  relationship lazy loads. A view cannot forget it, because views never add it.
* ``before_flush`` stamps new rows with the current tenant and refuses any write
  that would put a row in, or move a row to, a different tenant.

The current scope comes from, in order:

1. an explicit ``with tenant_scope(id):`` or ``with all_tenants():`` block;
2. the scope set for the current request (see ``set_request_scope``);
3. otherwise, **no access**: scoped queries return nothing and writes raise.

Failing closed means a forgotten scope shows an empty page, never another
carrier's data.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from flask import abort, g, has_app_context
from sqlalchemy import ForeignKey, event, inspect, select
from sqlalchemy.orm import (
    Mapped,
    ORMExecuteState,
    Session,
    declared_attr,
    mapped_column,
    with_loader_criteria,
)

from .extensions import db


class TenantViolation(RuntimeError):
    """Raised when a write would cross a tenant boundary."""


@dataclass(frozen=True)
class TenantScope:
    """What the current code is allowed to see.

    ``tenant_id`` set: one tenant. ``all_tenants`` true: every tenant (provider
    staff views, seed script, CLI). Neither: nothing.
    """

    tenant_id: int | None = None
    all_tenants: bool = False

    @property
    def is_restricted(self) -> bool:
        return not self.all_tenants


NO_ACCESS = TenantScope()
ALL_TENANTS = TenantScope(all_tenants=True)

# Placeholder that no real tenant uses; filtering on it returns zero rows.
_NO_TENANT_ID = -1

_override: ContextVar[TenantScope | None] = ContextVar("tenant_scope_override", default=None)


def current_scope() -> TenantScope:
    """Return the scope that queries and writes run under right now."""
    override = _override.get()
    if override is not None:
        return override
    if has_app_context():
        return g.get("tenant_scope", NO_ACCESS)
    return NO_ACCESS


def set_request_scope(scope: TenantScope) -> None:
    """Set the scope for the rest of this request. Called once per request by auth."""
    g.tenant_scope = scope


def clear_request_scope() -> None:
    g.pop("tenant_scope", None)


@contextmanager
def tenant_scope(tenant_id: int) -> Iterator[TenantScope]:
    """Run a block as a single tenant."""
    scope = TenantScope(tenant_id=tenant_id)
    token = _override.set(scope)
    try:
        yield scope
    finally:
        _override.reset(token)


@contextmanager
def all_tenants() -> Iterator[TenantScope]:
    """Run a block across every tenant.

    Only for provider-wide views (after a role check), the seed script and CLI
    commands. Every use should be easy to find with ``grep all_tenants``.
    """
    token = _override.set(ALL_TENANTS)
    try:
        yield ALL_TENANTS
    finally:
        _override.reset(token)


class TenantScoped:
    """Mixin for every table that holds one carrier's data."""

    # AuditLog sets this to True: provider-level actions have no tenant.
    __tenant_nullable__ = False

    @declared_attr
    def tenant_id(cls) -> Mapped[int]:
        return mapped_column(
            ForeignKey("tenants.id", ondelete="CASCADE"),
            index=True,
            nullable=cls.__tenant_nullable__,
        )


def scoped_get_or_404[T](model: type[T], record_id: int) -> T:
    """Load one tenant-scoped record by primary key, or 404.

    Use this instead of ``db.session.get`` / ``db.get_or_404``: those read the
    session's identity map first and can skip the tenant filter. A record that
    exists in another tenant returns 404, not 403, so its existence isn't
    confirmed.
    """
    obj = db.session.execute(select(model).where(model.id == record_id)).scalar_one_or_none()
    if obj is None or not _visible(obj, current_scope()):
        abort(404)
    return obj


def _visible(obj: object, scope: TenantScope) -> bool:
    if not isinstance(obj, TenantScoped):
        return True
    if scope.all_tenants:
        return True
    return scope.tenant_id is not None and obj.tenant_id == scope.tenant_id


# ---------------------------------------------------------------------------
# Session events
# ---------------------------------------------------------------------------


@event.listens_for(Session, "do_orm_execute")
def _filter_queries_by_tenant(state: ORMExecuteState) -> None:
    if not (state.is_select or state.is_update or state.is_delete):
        return
    scope = current_scope()
    if scope.all_tenants:
        return
    tenant_id = scope.tenant_id if scope.tenant_id is not None else _NO_TENANT_ID
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantScoped,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _guard_writes(session: Session, _flush_context, _instances) -> None:
    scope = current_scope()
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if not isinstance(obj, TenantScoped):
            continue
        _check_write(obj, scope, is_new=obj in session.new)


def _check_write(obj: TenantScoped, scope: TenantScope, *, is_new: bool) -> None:
    name = type(obj).__name__
    if scope == NO_ACCESS:
        raise TenantViolation(f"Write to {name} outside any tenant scope.")

    if scope.is_restricted:
        if is_new and obj.tenant_id is None:
            obj.tenant_id = scope.tenant_id
        if obj.tenant_id != scope.tenant_id and not (
            obj.__tenant_nullable__ and obj.tenant_id is None
        ):
            raise TenantViolation(
                f"{name} belongs to tenant {obj.tenant_id}, not current tenant {scope.tenant_id}."
            )
    elif obj.tenant_id is None and not obj.__tenant_nullable__:
        raise TenantViolation(f"New {name} needs an explicit tenant_id in all-tenants scope.")

    if not is_new:
        history = inspect(obj).attrs.tenant_id.history
        if history.deleted and history.deleted[0] is not None:
            raise TenantViolation(f"{name} cannot move between tenants.")

    _check_parents_match(obj)


def _check_parents_match(obj: TenantScoped) -> None:
    """A driver's test, a vehicle's DVIR, etc. must share the parent's tenant."""
    state = inspect(obj)
    for rel in state.mapper.relationships:
        if rel.direction.name != "MANYTOONE" or not issubclass(rel.mapper.class_, TenantScoped):
            continue
        parent = state.attrs[rel.key].loaded_value
        if parent is None or not isinstance(parent, TenantScoped):
            continue
        if parent.tenant_id is not None and parent.tenant_id != obj.tenant_id:
            raise TenantViolation(
                f"{type(obj).__name__} (tenant {obj.tenant_id}) links to "
                f"{type(parent).__name__} in tenant {parent.tenant_id}."
            )
