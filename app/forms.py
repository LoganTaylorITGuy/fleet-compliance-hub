"""Forms for editing compliance records. All POSTs carry a CSRF token."""

from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, SelectField, StringField
from wtforms.fields.choices import SelectChoice
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from .models import DriverStatus, ShopType


class DriverEditForm(FlaskForm):
    cdl_expiration = DateField("CDL expiration", validators=[Optional()])
    medical_card_expiration = DateField("Medical card expiration", validators=[Optional()])
    status = SelectField(
        "Status",
        choices=[
            SelectChoice(s.value, s.value.replace("_", " ").capitalize()) for s in DriverStatus
        ],
    )
    phone = StringField("Phone", validators=[Optional(), Length(max=30)])


class MaintenanceForm(FlaskForm):
    performed_on = DateField("Date", validators=[DataRequired()])
    work_done = StringField("Work done", validators=[DataRequired(), Length(max=300)])
    shop_type = SelectField(
        "Shop",
        choices=[
            SelectChoice(ShopType.IN_HOUSE.value, "In-house shop"),
            SelectChoice(ShopType.OUTSIDE.value, "Outside shop"),
        ],
    )
    shop_name = StringField("Shop name", validators=[Optional(), Length(max=120)])
    next_due_on = DateField("Next service due", validators=[Optional()])
    next_due_miles = IntegerField(
        "Next service due (miles)", validators=[Optional(), NumberRange(min=0, max=5_000_000)]
    )


class ActionForm(FlaskForm):
    """Empty form for one-click POST actions (complete repair, mark course done)."""
