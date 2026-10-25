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

```
crosstax-ai/
├── backend/          # Python FastAPI service (uv-managed)
│   ├── main.py       # App entry, CORS, lifespan
│   ├── core/         # Database abstraction (database.py), config (config.py)
│   ├── api/          # Routes, schemas, websocket
│   ├── agents/       # Pipeline agents (vision, TIN, indicia, verdict, audit)
│   ├── engine/       # Rule engine, data models
│   ├── models/       # SQLAlchemy ORM models (audit_session, merchant, etc.)
│   └── utils/        # File hash, logger
├── frontend/         # React 18 + TypeScript + Vite (npm-managed)
│   └── src/
│       ├── api/      # Axios client wrappers
│       ├── components/  # UI components (one folder per component)
│       ├── pages/    # Page-level components
│       ├── hooks/    # Custom hooks (useAuditStream, useRules, etc.)
│       ├── stores/   # Zustand stores
│       ├── types/    # TypeScript type definitions
│       └── styles/   # Theme tokens, global CSS
├── assets/           # Shared: Mock data + Jinja2 report templates
├── rules/            # CRS rule JSON configs (backend consumes)
├── tests/            # Mirrors backend/ and frontend/ structure
├── design/           # Design documents (DO NOT edit from code agent)
├── docs/             # Supporting docs (DO NOT edit from code agent)
├── specs/            # Requirements: PRD, data spec, ADRs (DO NOT edit from code agent)
├── pyproject.toml    # Backend dependencies (uv)
├── Dockerfile        # Multi-stage: frontend build → backend serves static
└── docker-compose.yml
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
- Database: all persistence through `backend/core/database.py` — SQLAlchemy ORM only, no raw SQL dialect features
- Models: one file per table in `backend/models/`, inherit from `Base` in `backend/core/database.py`
- Migrations: Alembic, generate via `alembic revision --autogenerate`, test on both SQLite and PG

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
- **DO NOT** use PG-specific SQL syntax directly — go through `backend/core/database.py` abstraction (ADR-008: SQLite dev + PG production)
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
