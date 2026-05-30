# Contributing

Thanks for your interest. This is a small research project, so the workflow is intentionally lightweight.

## Workflow

1. Open an issue first for anything beyond a typo or one-line bug fix — it saves both of us from wasted work.
2. Branch from `main`. Name branches by intent: `feat/...`, `fix/...`, `security/...`, `docs/...`, `refactor/...`, `chore/...`.
3. Keep commits small and focused. One concern per commit.
4. Use **conventional commit** subject lines: `type(scope): subject`. Examples:
   - `feat(roles): add bulk import of personnel from CSV`
   - `fix(camera): release VideoCapture on app shutdown`
   - `security(auth): require admin password change on first login`
   - `docs(readme): update Docker quickstart for ARM hosts`
5. Open a PR. CI runs `ruff check` and a `create_app()` smoke test. Both must pass.
6. PRs touching security-relevant code (auth, CSRF, file handling, DB models, the recognition engine) need a brief note in the description on what you tested.

## Code style

- Python: `ruff check access_control` must pass. Defaults are fine — no extra config beyond what's in the workflow.
- Templates: use the existing pattern. CSRF token hidden input goes immediately after every `<form method="post" ...>`.
- No `pickle` of any DB content. Ever.

## Reporting security issues

See [SECURITY.md](SECURITY.md). Email rather than file public issues.

## License

By contributing you agree your contributions are licensed under the [Apache License 2.0](LICENSE).
