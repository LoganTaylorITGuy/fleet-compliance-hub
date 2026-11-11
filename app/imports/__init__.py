"""Spreadsheet import: upload, map columns, review and fix rows, commit, undo."""

from flask import Blueprint

bp = Blueprint("imports", __name__, url_prefix="/import")

from . import routes  # noqa: E402, F401
