"""Fleet Compliance Hub: Flask application factory."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template

from .config import Config, resolve_secret_key
from .extensions import csrf, db, login_manager, migrate


def create_app(config_object: type[Config] | None = None, **overrides) -> Flask:
    """Build and configure a Flask app.

    ``config_object`` defaults to :class:`Config` (environment driven). Tests pass
    :class:`TestConfig`. Keyword ``overrides`` win over both.
    """
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)
    app.config.update(overrides)
    app.config["SECRET_KEY"] = resolve_secret_key(app.config)

    if app.config.get("DEMO_MODE") and app.config.get("APP_ENV") == "production":
        raise RuntimeError("DEMO_MODE must not be enabled in production.")

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    from . import models  # noqa: F401  (register tables with SQLAlchemy metadata)

    migrate.init_app(
        app,
        db,
        directory=str(Path(__file__).resolve().parent.parent / "migrations"),
        render_as_batch=True,  # lets Alembic alter tables on SQLite
        compare_type=True,
    )
    login_manager.init_app(app)
    csrf.init_app(app)

    _register_blueprints(app)
    _register_template_globals(app)
    _register_error_handlers(app)
    _register_security_headers(app)
    return app


def _register_blueprints(app: Flask) -> None:
    from .audit import bp as audit_bp
    from .auth import bp as auth_bp
    from .main import bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(audit_bp)


def _register_template_globals(app: Flask) -> None:
    from flask import g
    from flask_login import current_user

    from .auth.forms import LogoutForm, SwitchTenantForm
    from .auth.services import provider_tenants
    from .formatting import register_filters
    from .navigation import visible_nav_items
    from .permissions import ROLE_LABELS, can_edit, can_view, is_provider

    register_filters(app)

    @app.context_processor
    def inject_globals() -> dict:
        return {
            "provider_name": app.config["PROVIDER_NAME"],
            "demo_mode": app.config["DEMO_MODE"],
            "nav_items": visible_nav_items,
            "active_tenant": g.get("active_tenant"),
            "can_view": lambda area: can_view(current_user, area),
            "can_edit": lambda area: can_edit(current_user, area),
            "is_provider_user": current_user.is_authenticated and is_provider(current_user),
            "provider_tenants": lambda: provider_tenants(current_user),
            "role_label": ROLE_LABELS.get(getattr(current_user, "role", None), ""),
            "logout_form": LogoutForm,
            "switch_form": SwitchTenantForm,
        }


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(_error):
        return render_template(
            "error.html", code=403, message="You don't have access to that."
        ), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("error.html", code=404, message="We couldn't find that page."), 404


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'none'; form-action 'self'",
        )
        return response
