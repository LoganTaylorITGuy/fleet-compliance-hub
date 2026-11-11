from __future__ import annotations

from flask import abort, current_app, flash, g, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from .. import audit
from ..extensions import db, login_manager
from ..models import utcnow
from ..permissions import is_provider
from ..tenancy import all_tenants, clear_request_scope, set_request_scope, tenant_scope
from . import bp
from .forms import DemoLoginForm, LoginForm, LogoutForm, SwitchTenantForm
from .services import (
    ACTIVE_TENANT_KEY,
    DEMO_PERSONAS,
    authenticate,
    find_user_by_email,
    load_user,
    resolve_scope,
    safe_next_url,
    tenant_for_provider,
)

# Endpoints reachable without logging in.
PUBLIC_ENDPOINTS = {"auth.login", "auth.demo_login", "main.healthz", "static"}

login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"
login_manager.user_loader(load_user)


@bp.before_app_request
def require_login_and_set_scope():
    """Runs before every request: enforce login, then set the tenant scope."""
    clear_request_scope()
    g.active_tenant = None
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None
    if not current_user.is_authenticated:
        return login_manager.unauthorized()
    scope, tenant = resolve_scope(current_user)
    set_request_scope(scope)
    g.active_tenant = tenant
    return None


@bp.teardown_app_request
def _clear_scope(_exc):
    clear_request_scope()


def _finish_login(user, next_url: str | None = None):
    login_user(user)
    session.pop(ACTIVE_TENANT_KEY, None)
    user.last_login_at = utcnow()
    # Carrier logins are logged in their tenant; provider logins have no tenant.
    with tenant_scope(user.tenant_id) if user.tenant_id else all_tenants():
        audit.record("login", f"{user.name} logged in", user_id=user.id)
        db.session.commit()
    return redirect(safe_next_url(next_url) or url_for("main.index"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = LoginForm(next=request.args.get("next", ""))
    if form.validate_on_submit():
        user = authenticate(form.email.data, form.password.data)
        if user:
            return _finish_login(user, form.next.data)
        flash("That email and password don't match an active account.", "error")
    demo_forms = (
        {key: DemoLoginForm(persona=key) for key in DEMO_PERSONAS}
        if current_app.config["DEMO_MODE"]
        else {}
    )
    return render_template(
        "auth/login.html", form=form, demo_forms=demo_forms, personas=DEMO_PERSONAS
    )


@bp.post("/login/demo")
def demo_login():
    if not current_app.config["DEMO_MODE"]:
        abort(404)
    form = DemoLoginForm()
    if not form.validate_on_submit() or form.persona.data not in DEMO_PERSONAS:
        abort(400)
    email = DEMO_PERSONAS[form.persona.data][0]
    user = find_user_by_email(email)
    if user is None or not user.active:
        flash("Demo users aren't loaded yet. Run python seed.py first.", "error")
        return redirect(url_for("auth.login"))
    return _finish_login(user)


@bp.post("/logout")
@login_required
def logout():
    if not LogoutForm().validate_on_submit():
        abort(400)
    logout_user()
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for("auth.login"))


@bp.post("/switch-tenant")
@login_required
def switch_tenant():
    """Provider staff pick which carrier they're working in."""
    if not is_provider(current_user):
        abort(403)
    form = SwitchTenantForm()
    if not form.validate_on_submit():
        abort(400)
    tenant = tenant_for_provider(current_user, form.tenant_id.data)
    if tenant is None:
        abort(404)
    session[ACTIVE_TENANT_KEY] = tenant.id
    with tenant_scope(tenant.id):
        audit.record("switch_tenant", f"{current_user.name} opened {tenant.name}")
        db.session.commit()
    target = safe_next_url(request.form.get("next"))
    return redirect(target or url_for("main.index"))


@bp.post("/switch-tenant/clear")
@login_required
def clear_tenant():
    if not is_provider(current_user):
        abort(403)
    if not LogoutForm().validate_on_submit():
        abort(400)
    session.pop(ACTIVE_TENANT_KEY, None)
    return redirect(url_for("main.index"))
