# AGENTS.md

## Cursor Cloud specific instructions

### Architecture

Two-tier monorepo: Python FastAPI backend (`backend/`) and Next.js 14 frontend (`frontend/`). Infrastructure services run via Docker Compose from the root `docker-compose.yml`.

### Services overview

| Service | How to run | Port |
|---|---|---|
| **PostgreSQL** | `sudo docker compose up -d postgres` | 5432 |
| **Neo4j** | `sudo docker compose up -d neo4j` | 7474 (HTTP), 7687 (Bolt) |
| **Redis** | `sudo docker compose up -d redis` | 6379 |
| **Qdrant** | `sudo docker compose up -d qdrant` | 6333 |
| **Backend** | `cd backend && uvicorn main:app --host 0.0.0.0 --port 8000` | 8000 |
| **Frontend** | `cd frontend && npm run dev` | 3000 |

### Starting all infrastructure

```bash
sudo dockerd &>/tmp/dockerd.log &
sleep 3
sudo docker compose up -d   # from repo root
```

### Database initialization gotcha

The Alembic migrations are incomplete — the initial migration (`305f474fb39f`) creates tech-debt tables that reference `repositories` and `services` tables, but no migration creates those base tables. On a fresh database you must create all tables via SQLAlchemy first, then stamp Alembic:

```bash
cd backend
python3 -c "
import sys; sys.path.insert(0, '.')
from models.repository import *; from models.service import *; from models.tech_debt import *
from core.database import Base, engine
Base.metadata.create_all(engine)
"
alembic stamp head
```

### Frontend notes

- The root `.gitignore` previously had `lib/` which blocked `frontend/lib/` from appearing in the working tree. This was fixed to `/lib/` (root-only).
- `frontend/lib/utils.ts` was missing from the repo and has been added. It provides the standard `cn()` utility (clsx + tailwind-merge).
- ESLint config: `frontend/.eslintrc.json` must exist with `{"extends": "next/core-web-vitals"}`. The `eslint-config-next` version must match Next.js (currently v14).
- The frontend `.env.local` for local dev should have `NEXT_PUBLIC_API_URL=http://localhost:8000` (not including `/api`). The `next.config.js` rewrites proxy `/api/*` to the backend.
- `npm install --legacy-peer-deps` is required due to peer dependency conflicts between `eslint-config-next@14` and `eslint@8`.

### Backend notes

- **Do NOT use `--reload`** when running the backend with `uvicorn`. The repo clone step writes files into `backend/repositories/`, which triggers uvicorn's file watcher to restart the process, wiping the in-memory `active_analyses` dict and losing all analysis state. Run without `--reload` for stability.
- No test framework or linter is configured for the backend.
- Config defaults in `backend/core/config.py` match Docker Compose credentials — no `.env` file is needed for local dev.
- `OPENAI_API_KEY` and `GITHUB_TOKEN` are optional; features degrade gracefully without them.
- The backend runs Alembic `upgrade head` on startup via `init_db()`.
- Analysis completes with status "paused" when the human_review_agent creates checkpoints for ambiguous dependencies. This is expected human-in-the-loop behavior.

### Lint / Build / Test

- **Frontend lint**: `cd frontend && npm run lint`
- **Frontend build**: `cd frontend && npm run build` (has a pre-existing type error in `DebtList.tsx` — `Type 'unknown' is not assignable to type 'Key'`)
- **Backend**: No automated tests or linter configured.
