"""Forms for login, the demo role switcher, tenant switching and logout (all CSRF-protected)."""

from flask_wtf import FlaskForm
from wtforms import EmailField, HiddenField, IntegerField, PasswordField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    email = EmailField("Email", validators=[DataRequired(), Length(max=254)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=200)])
    next = HiddenField()


class DemoLoginForm(FlaskForm):
    """One-click login as a seeded demo user. Only rendered when DEMO_MODE is on."""

    persona = HiddenField(validators=[DataRequired()])


class SwitchTenantForm(FlaskForm):
    tenant_id = IntegerField("Carrier", validators=[DataRequired()])


class LogoutForm(FlaskForm):
    """Empty form: logout is a POST so it carries a CSRF token."""
