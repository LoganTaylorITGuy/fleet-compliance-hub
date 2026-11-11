from __future__ import annotations

from flask import abort, flash, g, redirect, render_template, request, url_for
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import select
from werkzeug.utils import secure_filename

from ..extensions import db
from ..forms import ActionForm
from ..models import ImportRun, ImportTemplate
from ..permissions import require_edit, require_view
from ..tenancy import scoped_get_or_404
from ..views import tenant_required
from . import bp, engine, staging
from .parsing import ImportFileError, read_table
from .specs import SPECS, suggest_mapping

PREVIEW_ROWS = 5


@bp.get("/")
@require_view("imports")
@tenant_required
def index():
    runs = db.session.scalars(select(ImportRun).order_by(ImportRun.id.desc()).limit(20)).all()
    templates = db.session.scalars(
        select(ImportTemplate).order_by(ImportTemplate.data_type, ImportTemplate.name)
    ).all()
    latest = engine.latest_run()
    return render_template(
        "imports/index.html",
        specs=SPECS,
        runs=runs,
        templates=templates,
        latest_id=latest.id if latest else None,
        form=FlaskForm(),
        action_form=ActionForm(),
    )


@bp.post("/")
@require_edit("imports")
@tenant_required
def upload():
    if not FlaskForm().validate_on_submit():
        abort(400)
    data_type = request.form.get("data_type", "")
    upload_file = request.files.get("file")
    if data_type not in SPECS or upload_file is None or not upload_file.filename:
        flash("Choose what the file holds and a file to upload.", "error")
        return redirect(url_for("imports.index"))
    file_name = secure_filename(upload_file.filename) or "upload"
    try:
        headers, rows = read_table(file_name, upload_file.read())
    except ImportFileError as exc:
        flash(str(exc), "error")
        return redirect(url_for("imports.index"))

    mapping = suggest_mapping(SPECS[data_type], headers)
    template_id = request.form.get("template_id", type=int)
    if template_id:
        template = scoped_get_or_404(ImportTemplate, template_id)
        if template.data_type == data_type:
            mapping = {h: template.column_mapping.get(h, mapping.get(h, "")) for h in headers}
    staged = staging.create(
        tenant_id=g.active_tenant.id,
        user_id=current_user.id,
        data_type=data_type,
        file_name=file_name,
        headers=headers,
        rows=rows,
        mapping=mapping,
    )
    return redirect(url_for("imports.map_columns", token=staged.token))


@bp.route("/<token>/map", methods=["GET", "POST"])
@require_edit("imports")
@tenant_required
def map_columns(token: str):
    staged = staging.load(token)
    spec = SPECS[staged.data_type]
    form = FlaskForm()
    if request.method == "POST":
        if not form.validate_on_submit():
            abort(400)
        valid = set(spec.field_names)
        mapping = {}
        for i, header in enumerate(staged.headers):
            target = request.form.get(f"col_{i}", "")
            mapping[header] = target if target in valid else ""
        chosen = [t for t in mapping.values() if t]
        if len(chosen) != len(set(chosen)):
            flash("Each field can only come from one column.", "error")
        else:
            staged.mapping = mapping
            staging.save(staged)
            _maybe_save_template(spec, mapping)
            return redirect(url_for("imports.review", token=token))
    return render_template(
        "imports/map.html",
        staged=staged,
        spec=spec,
        preview=staged.rows[:PREVIEW_ROWS],
        form=form,
    )


def _maybe_save_template(spec, mapping: dict[str, str]) -> None:
    name = request.form.get("template_name", "").strip()[:80]
    if not name:
        return
    template = db.session.scalars(
        select(ImportTemplate).where(
            ImportTemplate.data_type == spec.key, ImportTemplate.name == name
        )
    ).first()
    if template is None:
        template = ImportTemplate(name=name, data_type=spec.key, created_by_id=current_user.id)
        db.session.add(template)
    template.column_mapping = mapping
    db.session.commit()
    flash(f'Saved column mapping as template "{name}".', "success")


@bp.route("/<token>/review", methods=["GET", "POST"])
@require_edit("imports")
@tenant_required
def review(token: str):
    staged = staging.load(token)
    spec = SPECS[staged.data_type]
    form = FlaskForm()
    if request.method == "POST":
        if not form.validate_on_submit():
            abort(400)
        _apply_fixes(staged, spec)
        staging.save(staged)

    results = engine.build_rows(
        spec, staged.headers, staged.rows, staged.mapping, staged.overrides, set(staged.skipped)
    )
    blocking = [r for r in results if r.errors and not r.skipped]

    if request.method == "POST" and request.form.get("action") == "import":
        if blocking:
            flash("Fix or skip the highlighted rows before importing.", "error")
        else:
            run = engine.commit(spec, results, file_name=staged.file_name, user_id=current_user.id)
            staging.discard(token)
            flash(
                f"Imported {staged.file_name}: {run.rows_added} added, "
                f"{run.rows_updated} updated, {run.rows_skipped} skipped.",
                "success",
            )
            return redirect(url_for("imports.index"))

    mapped_fields = [f for f in spec.fields if f.name in staged.mapping.values()]
    return render_template(
        "imports/review.html",
        staged=staged,
        spec=spec,
        results=results,
        blocking=blocking,
        mapped_fields=mapped_fields,
        counts={
            "to_add": sum(1 for r in results if r.ok and r.action == "add"),
            "to_update": sum(1 for r in results if r.ok and r.action == "update"),
            "skipped": sum(1 for r in results if r.skipped),
            "errors": len(blocking),
        },
        form=form,
    )


def _apply_fixes(staged: staging.StagedImport, spec) -> None:
    """Store edited cell values and skip choices from the review form."""
    valid = set(spec.field_names)
    skipped = set()
    for key, value in request.form.items():
        if key.startswith("skip_") and key[5:].isdigit():
            skipped.add(int(key[5:]))
        elif key.startswith("fix_"):
            _, index, name = key.split("_", 2)
            if index.isdigit() and name in valid and int(index) < len(staged.rows):
                staged.overrides.setdefault(index, {})[name] = value.strip()[:300]
    staged.skipped = sorted(skipped)


@bp.post("/<token>/cancel")
@require_edit("imports")
@tenant_required
def cancel(token: str):
    if not FlaskForm().validate_on_submit():
        abort(400)
    staging.load(token)  # 404 unless it belongs to this tenant
    staging.discard(token)
    flash("Import cancelled. Nothing was changed.", "success")
    return redirect(url_for("imports.index"))


@bp.post("/runs/<int:run_id>/undo")
@require_edit("imports")
@tenant_required
def undo(run_id: int):
    if not ActionForm().validate_on_submit():
        abort(400)
    run = scoped_get_or_404(ImportRun, run_id)
    latest = engine.latest_run()
    if latest is None or latest.id != run.id:
        flash("Only the most recent import can be undone.", "error")
        return redirect(url_for("imports.index"))
    removed, restored = engine.undo(run)
    flash(f"Undid {run.file_name}: {removed} removed, {restored} restored.", "success")
    return redirect(url_for("imports.index"))


@bp.post("/templates/<int:template_id>/delete")
@require_edit("imports")
@tenant_required
def delete_template(template_id: int):
    if not ActionForm().validate_on_submit():
        abort(400)
    template = scoped_get_or_404(ImportTemplate, template_id)
    db.session.delete(template)
    db.session.commit()
    flash(f'Deleted template "{template.name}".', "success")
    return redirect(url_for("imports.index"))
