"""Uploads waiting to be mapped and reviewed, kept on disk between steps.

Each staged import is a JSON file named by a random token. It records the
tenant and user that uploaded it, and is only loaded back for that same
tenant, so a token can't be used from another carrier's session.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path

from flask import abort, current_app

from ..tenancy import current_scope

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,40}$")


@dataclass
class StagedImport:
    token: str
    tenant_id: int
    user_id: int
    data_type: str
    file_name: str
    headers: list[str]
    rows: list[list[str]]
    mapping: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    skipped: list[int] = field(default_factory=list)


def _folder() -> Path:
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _path(token: str) -> Path:
    if not TOKEN_PATTERN.fullmatch(token):
        abort(404)
    return _folder() / f"{token}.json"


def create(**fields) -> StagedImport:
    staged = StagedImport(token=secrets.token_urlsafe(18), **fields)
    save(staged)
    return staged


def save(staged: StagedImport) -> None:
    _path(staged.token).write_text(json.dumps(asdict(staged)), encoding="utf-8")


def load(token: str) -> StagedImport:
    """Load a staged import for the current tenant, or 404."""
    path = _path(token)
    if not path.exists():
        abort(404)
    staged = StagedImport(**json.loads(path.read_text(encoding="utf-8")))
    if staged.tenant_id != current_scope().tenant_id:
        abort(404)
    return staged


def discard(token: str) -> None:
    _path(token).unlink(missing_ok=True)
