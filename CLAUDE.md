# Cloud Cost Optimizer and Remediation Engine — Technical Brief

## Project

Cloud Cost Optimizer and Remediation Engine. Ingests AWS and Azure billing exports, identifies orphaned resources, generates decommission CLI commands, exposes findings via API and dashboard.

## Stack

- Python 3.12.5 (3.14.0a3 was requested but pydantic-core has no compatible wheel for 3.14 alpha; switched with user approval — see prompts.md turn 3)
- uv for dependency management
- FastAPI
- SQLAlchemy 2.0 with SQLite
- Pydantic v2 for API schemas
- pandas for CSV parsing
- Jinja2 with HTMX for the dashboard
- Chart.js via CDN for visualisations
- pytest for tests

## Dependency Management

- Always use `uv add <package>` to add dependencies.
- Never write version strings, never edit pyproject.toml manually, never use pip.
- If a version constraint is genuinely needed, run `uv pip index versions <package>` first to confirm versions that exist on PyPI — never invent version numbers from memory.
- Run code via `uv run` and tests via `uv run pytest`.
- pyproject.toml must declare `requires-python = ">=3.12"`.
- If `uv add` fails due to a Python 3.14 incompatibility, report it immediately rather than silently downgrading Python or working around it.

## Code Conventions

- Type hints on every function and method.
- SQLAlchemy models in `models/db.py` and Pydantic schemas in `models/schemas.py` — kept strictly separate.
- Async FastAPI endpoints where IO-bound.
- Dependency injection for the database session via a `get_session` FastAPI dependency.
- Structured logging via the standard `logging` module.
- No commented-out code, no TODOs left behind — either implement it or remove it.

## Testing

- Write tests alongside implementation in the same turn, not in a separate pass.
- Use pytest.
- Test the business logic that matters: parsers (correct normalisation, malformed input handled), rules engine (each rule has at least one positive and one negative case), and one end-to-end API integration test that ingests a sample fixture and verifies findings appear via the API.
- Do not test framework plumbing, dashboard rendering, trivial getters, or SQLAlchemy model definitions.
- Aim for tests that read like specifications — clear names, one assertion of behaviour per test where practical.
- Tests live in `tests/` mirroring the `app/` structure.
- Run with `uv run pytest`.

## Architecture

- Parsers normalise provider-specific exports into a common `Resource` schema.
- A rules engine evaluates orphan patterns producing `Finding`s.
- A command generator emits decommission CLI commands attached to `Finding`s.
- FastAPI exposes ingest, list, detail, and summary endpoints.
- A Jinja and HTMX dashboard renders the findings.

## Git Workflow

- Commit per architectural step using Conventional Commits format (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- Subject line under 72 characters, imperative mood, no trailing full stop.
- Body explains the why, not the what, in 2–4 lines.
- Reference the `prompts.md` turn number when relevant (e.g. `Ref: prompts.md turn 6`).
- Group implementation with its tests in the same commit.
- Split unrelated changes into separate commits.
- At the end of any turn that produces code changes, automatically propose a commit message before completing the response — do not commit until approved.
- Never amend pushed commits, never force push, never rewrite history.

## Workflow Rules

- No manual edits — all logic and fixes are provided here.
- Elapsed time reported at the end of every response.
- `prompts.md` is strictly append-only and chronological. Each new turn is appended at the very end of the file, under a heading `## Turn N — <short descriptor>` where N is exactly one greater than the previous final turn number. Before writing any new entry, read the current final turn number in `prompts.md` and increment from there. Never insert between existing turns. Never re-number. Never re-group by topic. Never reorder. If you believe a reorder would improve readability, do not — propose it to the user first. Chronological order is non-negotiable: `prompts.md` is the audit log of architectural decisions in the order they were made; reordering destroys its value.
