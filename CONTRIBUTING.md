# Contributing to Sentinel of Mnemosyne

Thanks for contributing.

## Ground rules

- Be respectful and constructive.
- Keep PRs focused and small.
- Update docs/tests with code changes.
- Never commit secrets.

## Before you start

1. Search existing issues/PRs first.
2. For bugs/features, open an issue using the templates.
3. For security issues, use `SECURITY.md` (do not file public issues).

## Local setup

```bash
git clone https://github.com/The-Artificer-of-Ciphers-LLC/sentinel-of-mnemosyne.git
cd sentinel-of-mnemosyne
cp .env.example .env
```

Run tests:

```bash
cd sentinel-core
pytest
```

## Branch + PR workflow

1. Fork the repo.
2. Create a branch from `main`:
   - `fix/<short-name>` or `feat/<short-name>`
3. Commit with clear messages.
4. Push to your fork.
5. Open a PR to `main` using the PR template.

## PR requirements (enforced)

- PR review required
- CODEOWNERS review required
- 1 approval minimum
- Latest push must be approved
- Required checks must pass: `test`, `docker-build`
- All review conversations resolved

Only the maintainer can merge to `main`.

## Issues

Use GitHub issue forms:

- **Bug Report** for defects (include repro steps + environment)
- **Feature Request** for improvements

Questions/discussion: GitHub Discussions.

## Documentation expectations

If behavior changes, update relevant docs (README + docs/*) in the same PR.

## Developer Certificate / sign-off

Not required for now.
