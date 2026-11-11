## What changed

<!-- One or two sentences. Link the build step or issue. -->

## Why

## Testing checklist

- [ ] `ruff check . && ruff format --check .` passes
- [ ] `pytest` passes locally (coverage did not drop)
- [ ] Tenant isolation tests pass (`pytest tests/test_tenant_isolation.py`)
- [ ] Schema changes include an Alembic migration (`flask db migrate`), and `flask db upgrade` works on a fresh database
- [ ] New pages checked at phone width (375 px) and with keyboard only
- [ ] No secrets, real customer data, or real company identifiers committed
- [ ] CHANGELOG updated
