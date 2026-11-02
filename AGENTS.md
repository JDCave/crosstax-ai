# CrossTax AI — Agent Coding Instructions

> This file is read by AI coding assistants (Copilot, Cursor, Claude Code, etc.) before writing code.
> All team members' agents MUST follow these conventions.

## Spec-First Workflow

Before writing any code, read and follow these documents:

1. **PRD** — `specs/prd.md` — feature requirements, acceptance criteria, 5 test cases
2. **Architecture** — `design/architecture.md` — layering, ADRs, data models, agent contracts
3. **Data Spec** — `specs/data-spec.md` — shared data contracts (CRSFormData, AuditIssue, AuditSession)
4. **UI Spec** — `design/ui-spec.md` — component specs, layout, color tokens, interaction patterns

If a spec is ambiguous or missing, ask the team before inventing behavior. Do not silently deviate.

## Repository Structure (Monorepo)

This is a **single repository** containing both frontend and backend as peer modules.
Entries marked **(planned)** do not exist yet — do not assume you can import from them.

```
crosstax-ai/
├── backend/          # Python FastAPI service (uv-managed)
│   ├── main.py       # App factory create_app(), CORS, lifespan, router registration
│   ├── core/
│   │   ├── config.py # pydantic-settings: Settings / DatabaseSettings / RedisSettings
│   │   └── logging/  # setup_logging, formatter, RequestIdMiddleware
│   ├── infrastructure/
│   │   ├── database.py   # Async engine + async_sessionmaker + get_session() dependency
│   │   └── exceptions.py # register_exception_handlers()
│   ├── api/
│   │   ├── routes/   # health.py (live); audit/rules/cases (planned)
│   │   ├── schemas/  # Pydantic request/response models (planned)
│   │   └── websocket.py # /ws/audit/{session_id} (planned)
│   ├── models/       # SQLAlchemy ORM models
│   │   ├── base.py   # DeclarativeBase + TimestampMixin — Alembic targets this
│   │   └── user.py   # audit_session.py / merchant.py (planned)
│   ├── repositories/ # base.py repository pattern
│   ├── agents/       # Pipeline agents: vision, TIN, indicia, verdict, audit (planned)
│   ├── engine/       # Rule engine + hot reload, data models (planned)
│   └── utils/        # File hash, helpers (planned)
├── alembic/          # Migrations: env.py (async-aware) + script.py.mako; versions/ empty
├── frontend/         # React 18 + TypeScript + Vite (npm-managed) — **planned, not created**
│   └── src/
│       ├── api/      # Axios client wrappers
│       ├── components/  # UI components (one folder per component)
│       ├── pages/    # Page-level components
│       ├── hooks/    # Custom hooks (useAuditStream, useRules, etc.)
│       ├── stores/   # Zustand stores
│       ├── types/    # TypeScript type definitions
│       └── styles/   # Theme tokens, global CSS
├── assets/           # Shared: Mock data + Jinja2 report templates (placeholders only)
├── rules/            # CRS rule JSON configs, backend consumes (planned, dir empty)
├── tests/            # Mirrors backend/ (tests/backend/); tests/frontend/ planned
├── design/           # Design documents (DO NOT edit from code agent)
├── docs/             # Supporting docs — proposal/ only (DO NOT edit from code agent)
├── specs/            # Requirements: PRD, data spec, ADRs (DO NOT edit from code agent)
├── pyproject.toml    # Backend dependencies + ruff/mypy/pytest/coverage config (uv)
├── uv.lock           # uv lockfile — commit it, never hand-edit
├── alembic.ini       # Alembic configuration
├── Makefile          # Canonical command entry points (see below)
├── Dockerfile        # uv multi-stage backend image, non-root (frontend stage planned)
├── docker-compose.yml # backend + postgres:16 + redis:7
├── .env.example      # Env var template — copy to root .env
└── .pre-commit-config.yaml
```

## Development Commands

### Backend (Python / uv)

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
uv run pytest tests/backend/

# Lint
uv run ruff check backend/

# Type check
uv run mypy backend/
```

### Frontend (Node / npm)

> **Not yet created** — `frontend/` does not exist. Scaffold it first (ROADMAP §3.1) before using these commands.

```bash
cd frontend/

# Install dependencies
npm install

# Run development server
npm run dev

# Run tests
npm test

# Build for production
npm run build
```

### Docker

```bash
# Build and run
docker compose up --build

# Run tests
docker compose run --rm backend pytest
```

## Backend Conventions (Python / FastAPI)

- Python 3.11+, use type hints on all function signatures
- Package management: **uv** (not pip/poetry)
- Use `dataclass` or `pydantic.BaseModel` for data structures — match `specs/data-spec.md`
- Agent modules: one file per agent in `backend/agents/`, each exposes a single public class or function
- Rule engine: thread-safe hot reload via `threading.Lock`, version ID from content hash
- API routes: RESTful, versioned under `/api/v1/`, schemas in `backend/api/schemas/`
- WebSocket: single endpoint `/ws/audit/{session_id}`, push `PipelineStep` JSON messages
- Error responses: use HTTP status codes + JSON body `{ "code": "...", "message": "..." }`
- No business logic in route handlers — delegate to agents/engine
- Environment variables via `pydantic-settings` (see `.env.example`), never hardcode secrets
- Database: all persistence through `backend/infrastructure/database.py` — SQLAlchemy 2.0 **async** ORM only, no raw SQL dialect features
- Sessions: inject via the `get_session()` FastAPI dependency — never construct sessions manually in routes
- Connection URLs must carry the async driver prefix: `sqlite+aiosqlite://` (local) / `postgresql+asyncpg://` (PG)
- Pool limits are fixed by ADR-010 (`pool_size=3`, `max_overflow=0`) because Alibaba Cloud PG caps the team at 30 total connections; `tests/backend/test_config.py` asserts them — do not raise them
- Models: one file per table in `backend/models/`, inherit from `Base` in `backend/models/base.py` (Alembic autogenerate targets this)
- Migrations: Alembic, generate via `make migrate msg="..."` (`alembic revision --autogenerate`), test on both SQLite and PG

## Frontend Conventions (React / TypeScript)

- React 18, function components + hooks only, no class components
- TypeScript strict mode — no `any` unless absolutely necessary (and commented why)
- Ant Design 5.x for all UI primitives — do not introduce another UI library
- Component folder structure: `ComponentName/index.tsx` + optional `ComponentName.module.css`
- State management: Zustand for global state, `useState`/`useReducer` for local, TanStack Query for server state
- API calls: only through `frontend/src/api/` wrappers, never raw `fetch` in components
- WebSocket: encapsulated in `hooks/useAuditStream.ts`, components consume the hook
- Styling: CSS Modules + Ant Design theme tokens, no inline styles except Ant Design `style` prop for minor tweaks
- Follow component specs in `design/ui-spec.md` §4 for naming and behavior

## Guardrails

- **DO NOT** hardcode CRS rules — all rules come from JSON files in `rules/`
- **DO NOT** bypass the agent pipeline — all audit flows through `run_audit_pipeline()`
- **DO NOT** use PG-specific SQL syntax directly — go through the `backend/infrastructure/database.py` abstraction (ADR-008: SQLite dev + PG production)
- **DO NOT** call Vision API directly from routes — go through `VisionParserAgent`
- **DO NOT** modify files in `specs/`, `design/`, or `docs/` — those are PM/designer-owned
- **DO NOT** introduce new top-level dependencies without team agreement
- **DO NOT** split into multiple repos — this is a monorepo with peer modules
- **DO** keep the 5 demo cases working — any refactor must not break Case A–E
- **DO** use SQLAlchemy ORM types only — no raw SQL dialect features that break SQLite compatibility

## Testing

- Backend: `pytest` in `tests/backend/`, one test file per agent module
- Must-have tests: TIN validator (all algorithms), verdict resolver (3 verdicts), indicia reasoner, API routes, E2E pipeline (5 cases)
- Frontend: `vitest` + React Testing Library, test files co-located with source in `frontend/src/` (e.g. `components/VerdictBanner/__tests__/`)
- Must-have tests: VerdictBanner (3 states), PipelineStatus, useAuditStream hook
- Run `uv run pytest` and `cd frontend && npm test` before committing

## Naming

| Item | Convention | Example |
|------|-----------|---------|
| Python files | snake_case | `tin_validator.py` |
| Python classes | PascalCase | `TINValidatorEngine` |
| Python functions | snake_case | `run_audit_pipeline()` |
| TS/React files | PascalCase | `VerdictBanner.tsx` |
| TS hooks | camelCase, `use` prefix | `useAuditStream.ts` |
| TS types/interfaces | PascalCase | `AuditSession`, `Verdict` |
| API paths | kebab-case | `/api/v1/audit` |
| CSS modules | camelCase | `.verdictBanner` |
| Git branches | `type/short-desc` | `feat/tin-validator`, `fix/ws-reconnect` |
