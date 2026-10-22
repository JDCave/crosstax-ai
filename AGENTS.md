# CrossTax AI — Agent Coding Instructions

> This file is read by AI coding assistants (Copilot, Cursor, Claude Code, etc.) before writing code.
> All team members' agents MUST follow these conventions.

## Spec-First Workflow

Before writing any code, read and follow these documents:

1. **PRD** — `specs/crosstax-ai-prd.md` — feature requirements, acceptance criteria, 5 test cases
2. **Architecture** — `design/architecture-overview.md` — layering, ADRs, data models, agent contracts
3. **UI Spec** — `design/react-ui-spec.md` — component specs, layout, color tokens, interaction patterns

If a spec is ambiguous or missing, ask the team before inventing behavior. Do not silently deviate.

## Project Structure

```
crosstax-ai/
├── backend/          # Python FastAPI service
│   ├── main.py       # App entry, CORS, lifespan
│   ├── api/          # Routes, schemas, websocket
│   ├── agents/       # Pipeline agents (vision, TIN, indicia, verdict, audit)
│   ├── engine/       # Rule engine, data models
│   └── utils/        # File hash, logger
├── frontend/         # React 18 + TypeScript + Vite
│   └── src/
│       ├── api/      # Axios client wrappers
│       ├── components/  # UI components (one folder per component)
│       ├── pages/    # Page-level components
│       ├── hooks/    # Custom hooks (useAuditStream, useRules, etc.)
│       ├── stores/   # Zustand stores
│       ├── types/    # TypeScript type definitions
│       └── styles/   # Theme tokens, global CSS
├── assets/           # Mock data (mock_merchants.json, sample CRS files) + Jinja2 report templates
├── rules/            # CRS rule JSON configs (rules_v1_base.json, rules_v2_patch.json)
├── tests/            # Mirrors backend/ and frontend/ structure
├── design/           # Design documents (DO NOT edit from code agent)
├── docs/             # Supporting docs (DO NOT edit from code agent)
└── specs/            # Requirements (DO NOT edit from code agent)
```

## Backend Conventions (Python / FastAPI)

- Python 3.11+, use type hints on all function signatures
- Use `dataclass` or `pydantic.BaseModel` for data structures — match `design/architecture-overview.md` §2.2.1
- Agent modules: one file per agent in `backend/agents/`, each exposes a single public class or function
- Rule engine: thread-safe hot reload via `threading.Lock`, version ID from content hash
- API routes: RESTful, versioned under `/api/v1/`, schemas in `backend/api/schemas/`
- WebSocket: single endpoint `/ws/audit/{session_id}`, push `PipelineStep` JSON messages
- Error responses: use HTTP status codes + JSON body `{ "code": "...", "message": "..." }`
- No business logic in route handlers — delegate to agents/engine
- Environment variables via `pydantic-settings` or `os.environ`, never hardcode secrets

## Frontend Conventions (React / TypeScript)

- React 18, function components + hooks only, no class components
- TypeScript strict mode — no `any` unless absolutely necessary (and commented why)
- Ant Design 5.x for all UI primitives — do not introduce another UI library
- Component folder structure: `ComponentName/index.tsx` + optional `ComponentName.module.css`
- State management: Zustand for global state, `useState`/`useReducer` for local, TanStack Query for server state
- API calls: only through `frontend/src/api/` wrappers, never raw `fetch` in components
- WebSocket: encapsulated in `hooks/useAuditStream.ts`, components consume the hook
- Styling: CSS Modules + Ant Design theme tokens, no inline styles except Ant Design `style` prop for minor tweaks
- Follow component specs in `design/react-ui-spec.md` §4 for naming and behavior

## Guardrails

- **DO NOT** hardcode CRS rules — all rules come from JSON files in `rules/`
- **DO NOT** bypass the agent pipeline — all audit flows through `run_audit_pipeline()`
- **DO NOT** add database dependencies — storage is JSON files / SQLite only (ADR-003)
- **DO NOT** call Vision API directly from routes — go through `VisionParserAgent`
- **DO NOT** modify files in `specs/`, `design/`, or `docs/` — those are PM/designer-owned
- **DO NOT** introduce new top-level dependencies without team agreement
- **DO** keep the 5 demo cases working — any refactor must not break Case A–E

## Testing

- Backend: `pytest` in `tests/backend/`, one test file per agent module
- Must-have tests: TIN validator (all algorithms), verdict resolver (3 verdicts), indicia reasoner, API routes, E2E pipeline (5 cases)
- Frontend: `vitest` + React Testing Library, test files co-located with source in `frontend/src/` (e.g. `components/VerdictBanner/__tests__/`)
- Must-have tests: VerdictBanner (3 states), PipelineStatus, useAuditStream hook
- Run `pytest` and `npm test` before committing

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
