# Prompts Audit Log

---

## Turn 1

**Prompt:**
Lead Architect mode: ON. We are building a Python-based, API-first Cloud Cost Optimizer and Remediation Engine using a free database and a dashboard.
Rules:
• No Manual Edits: You provide all logic and fixes. I will not edit any code.
• Audit Log: You must maintain a file named prompts.md. After every turn, update that file (or provide the text block) with the prompt I just used.
• Time-Check: Start a timer. Goal is an MVP in 4-6 hours (Max window: 16h). Report 'Elapsed Time' at the end of every response. Acknowledge and let's start.

---

## Turn 4

**Prompt:**
approve this commit. You missed adding a .gitignore in the scaffold turn. Add one now at the repo root covering: Python artefacts (pycache/, *.pyc, .pyo, .pytest_cache/, .ruff_cache/, .mypy_cache/), virtual environments (.venv/, venv/), uv artefacts that shouldn't be tracked (note: uv.lock SHOULD be committed), the SQLite database files (.db, *.sqlite, .sqlite3), environment files (.env, .env.), OS noise (.DS_Store, Thumbs.db), IDE configs (.vscode/, .idea/, *.swp), build artefacts (build/, dist/, *.egg-info/), and any local upload directory if we have one.
Check the current git status — if any of these are already tracked, untrack them with git rm --cached and include that in the commit. Propose the commit message.

**Note:** Also removed uv init boilerplate root main.py (entrypoint is app/main.py). No tracked files were caught by the new .gitignore rules.

---

## Turn 3

**Prompt:**
approve the commit then
Scaffold the project. Initialise with uv init, set requires-python = ">=3.14" in pyproject.toml, then uv add each dependency listed in CLAUDE.md (fastapi, uvicorn, sqlalchemy, pydantic, pandas, jinja2, python-multipart for uploads, and pytest plus httpx as dev dependencies).
Create this directory structure:
app/
  main.py
  database.py
  models/
    db.py
    schemas.py
  parsers/
  rules/
  commands/
  api/
  web/
    templates/
    static/
sample_data/
tests/
Define the SQLAlchemy 2.0 declarative models in app/models/db.py using Mapped and mapped_column with proper type annotations:
Resource (id, provider, resource_type, region, resource_id, monthly_cost_usd, tags as JSON, last_active_date, raw_export as JSON, created_at)
Finding (id, resource_id FK, rule_name, severity, estimated_monthly_saving_usd, evidence as JSON, decommission_command, detected_at)
IngestionRun (id, source_file, provider, row_count, finding_count, created_at)
Define matching Pydantic v2 schemas in app/models/schemas.py for API request and response bodies, kept strictly separate from the SQLAlchemy models.
Set up the SQLite engine and session factory in app/database.py with a get_session FastAPI dependency. Create tables on app startup.
Propose the commit message at the end. Report elapsed time.

**Note:** Python 3.14.0a3 was incompatible with pydantic-core (missing C symbol _PyUnicode_DATA). Switched to Python 3.12.5 with user approval.

---

## Turn 2

**Prompt:**
Acknowledged. Before any feature code, let's establish the standing technical brief. Create CLAUDE.md at the repo root with the following sections:
Project
Cloud Cost Optimizer and Remediation Engine. Ingests AWS and Azure billing exports, identifies orphaned resources, generates decommission CLI commands, exposes findings via API and dashboard.
Stack
Python 3.14, uv for dependency management, FastAPI, SQLAlchemy 2.0 with SQLite, Pydantic v2 for API schemas, pandas for CSV parsing, Jinja2 with HTMX for the dashboard, Chart.js via CDN for visualisations, pytest for tests.
Dependency management
Always use uv add <package> to add dependencies. Never write version strings, never edit pyproject.toml manually, never use pip. If a version constraint is genuinely needed, run uv pip index versions <package> first to confirm versions that exist on PyPI — never invent version numbers from memory. Run code via uv run and tests via uv run pytest. pyproject.toml must declare requires-python = ">=3.14". If uv add fails due to a Python 3.14 incompatibility, report it immediately rather than silently downgrading Python or working around it.
Code conventions
Type hints on every function and method. SQLAlchemy models in models/db.py and Pydantic schemas in models/schemas.py kept strictly separate. Async FastAPI endpoints where IO bound. Dependency injection for the database session via a get_session FastAPI dependency. Structured logging via the standard logging module. No commented-out code, no TODOs left behind — either implement it or implement it or remove it.
Testing
Write tests alongside implementation in the same turn, not in a separate pass. Use pytest. Test the business logic that matters: parsers (correct normalisation, malformed input handled), rules engine (each rule has at least one positive and one negative case), and one end-to-end API integration test that ingests a sample fixture and verifies findings appear via the API. Do not test framework plumbing, dashboard rendering, trivial getters, or SQLAlchemy model definitions. Aim for tests that read like specifications — clear names, one assertion of behaviour per test where practical. Tests live in tests/ mirroring the app/ structure. Run with uv run pytest.
Architecture
Parsers normalise provider-specific exports into a common Resource schema. A rules engine evaluates orphan patterns producing Findings. A command generator emits decommission CLI commands attached to Findings. FastAPI exposes ingest, list, detail, and summary endpoints. A Jinja and HTMX dashboard renders the findings.
Git workflow
Commit per architectural step using Conventional Commits format (feat:, fix:, test:, docs:, chore:, refactor:). Subject line under 72 characters, imperative mood, no trailing full stop. Body explains the why, not the what, in 2 to 4 lines. Reference the prompts.md turn number when relevant (e.g. "Ref: prompts.md turn 6"). Group implementation with its tests in the same commit. Split unrelated changes into separate commits. At the end of any turn that produces code changes, automatically propose a commit message before completing the response — do not commit until I approve. Never amend pushed commits, never force push, never rewrite history.
Workflow rules (already acknowledged in the opening prompt)
No manual edits by me — you provide all logic and fixes. prompts.md maintained every turn with the prompt I just used. Elapsed time reported at the end of every response.
Create the file with these sections, then confirm. Do not scaffold the project yet — that's the next prompt.
