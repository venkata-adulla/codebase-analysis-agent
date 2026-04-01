# Repository Analysis Agent

An AI-assisted system for analyzing software repositories: clone or attach code, run a multi-agent pipeline, explore dependency graphs and architecture views, review technical debt, and ask questions about the codebase through a web UI.

## Features

- **Repository onboarding**: Clone from Git URLs (including GitHub), or use local paths; branches and shallow clones supported where configured.
- **Multi-language analysis**: Static analysis and parsers for Python, JavaScript/TypeScript, Java, and related ecosystems.
- **Service inventory**: Discovered modules/services with AI-generated or structural documentation, searchable from the Services area.
- **Dependency graph**: Interactive graph (React Flow) with service nodes, edges, filters, and optional temporal churn overlay on nodes.
- **Architecture views**: Summaries and diagrams derived from the graph and heuristics.
- **Impact analysis**: Heuristic blast-radius and risk signals from dependency structure and change context.
- **Temporal analysis**: Git history, merged PRs, and PR comments with drift statements, heatmap-style churn, and timeline; configurable sample sizes per request (defaults keep responses fast).
- **Technical debt**: Scored categories, issue lists, remediation-oriented views, and per-category explanations of how scores are derived (weights, normalization, coverage).
- **Cross-repository comparison**: Compare cached metrics across repositories.
- **Human review**: Resolve checkpoints when the pipeline pauses on ambiguous dependencies.
- **Codebase chat**: Grounded Q&A over service summaries and graph context (requires OpenAI).
- **Operator UI**: Top navigation, brand styling, and semantic action colors (primary, success, warning, destructive) for a consistent workflow.

## Architecture

| Layer | Technology |
|-------|------------|
| **API** | FastAPI, Alembic migrations on startup |
| **UI** | Next.js (App Router), Tailwind CSS, React Flow |
| **Relational data** | PostgreSQL (repositories, services, tech-debt artifacts, analysis metadata) |
| **Graph** | Neo4j (Bolt) for dependency graph storage and queries |
| **Cache & rate limiting** | Redis (report caching, chat cache, API rate-limit backend) |

Infrastructure for local development is defined in `docker-compose.yml` (PostgreSQL, Neo4j, Redis).

## Quick start

### Prerequisites

- Docker and Docker Compose (for databases)
- Python 3.10+
- Node.js 18+

### Backend

```bash
cd backend
pip install -r requirements.txt
```

From the repository root, start PostgreSQL, Neo4j, and Redis:

```bash
docker compose up -d postgres neo4j redis
```

Run the API (omit `--reload` if you run long analyses that clone into `backend/repositories/`, so in-memory analysis state is not reset on file writes):

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

Configure secrets and options via environment variables or `backend/.env` (see `backend/core/config.py`). `OPENAI_API_KEY` and `GITHUB_TOKEN` are optional but unlock more features.

If database migrations fail on a completely empty database, see [`AGENTS.md`](./AGENTS.md) for the one-time initialization notes.

### Frontend

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The app typically proxies API calls to the backend via `next.config.js`; set `NEXT_PUBLIC_API_URL` if you run the API on another origin.

## API documentation

With the backend running:

- Swagger UI: http://localhost:8000/docs  
- ReDoc: http://localhost:8000/redoc  

## Repository layout

```
├── backend/       # FastAPI application, agents, services, models
├── frontend/      # Next.js application
├── docker-compose.yml
├── AGENTS.md      # Maintainer notes (DB edge cases, dev constraints)
└── README.md
```

## License

MIT
