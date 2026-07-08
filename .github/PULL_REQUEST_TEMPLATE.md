<!-- Do not use PRs for security issues — see SECURITY.md. -->

## What & why

<!-- What does this change do, and why? Link any related issue. -->

Closes #

## Checklist

- [ ] Focused on a single change
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `mypy app` passes
- [ ] `uv run pytest` passes
- [ ] `cd web && ./node_modules/.bin/tsc --noEmit` passes (if the web app changed)
- [ ] Added/updated tests for the change
- [ ] Added an Alembic migration if a model changed (single head)
- [ ] Updated docs / CHANGELOG if user-facing
