# Contributing

Contributions are welcome — the knowledge base in particular grows best through many small, well-sourced additions.

## Setup

```bash
git clone https://github.com/wac0ku/fastapi-issue-hive.git
cd fastapi-issue-hive
uv sync
uv run pytest -v   # must be green before and after your change
```

## What to contribute

**Most valuable: knowledge-base entries.** New failure categories or sharper signals/fixes for existing ones — see [docs/04-knowledge-base.md](docs/04-knowledge-base.md) for the anatomy and quality guidelines. Every category change needs a triage test with a realistic issue text.

Also welcome:

- New issue sources (GitLab, Jira) as `app/services/` fetchers returning `list[IssueInput]`
- New workers (see the extension points in [docs/02-architecture.md](docs/02-architecture.md))
- Documentation fixes — docs are numbered chapters under `docs/`

## Ground rules

1. **Heuristic mode is sacred.** Every feature must work with zero API keys; Claude may only enhance, never gate. The test suite runs offline — keep it that way.
2. **Typed boundaries.** Data crossing a worker boundary is a Pydantic model in `app/schemas.py`, not a dict.
3. **Queen orchestrates, workers decide.** No scheduling in workers, no domain logic in `queen.py`.
4. **Tests accompany behavior.** Bug fix → regression test; new category → triage test; new endpoint → API test.

## Pull requests

- Branch from `main`, one topic per PR
- Conventional-commit style messages (`feat:`, `fix:`, `docs:`, `refactor:`)
- CI (pytest on Python 3.10 + 3.12) must pass
- If you changed triage behavior, paste a before/after analysis of a real issue in the PR description
