# Codebase Analysis Agent System

A production-ready AI agent system that analyzes legacy codebases across multiple languages, creates dependency graphs, documents services, and performs impact analysis.

## Features

- **Multi-Repository Analysis**: Support for GitHub repositories, local files, and Git clone
- **Multi-Language Support**: Python, Java, JavaScript/TypeScript, and more
- **Dependency Graph Generation**: Service-level dependencies, API endpoints, databases
- **Impact Analysis**: Change propagation analysis, breaking change detection, risk scoring
- **Human-in-the-Loop**: Agent checkpoints for ambiguous cases requiring human input
- **Documentation Generation**: AI-powered service documentation using OpenAI

## Architecture

- **Backend**: FastAPI with multi-agent orchestration
- **Frontend**: Next.js 14+ with React Flow for visualizations
- **Databases**: Neo4j (graph), PostgreSQL (metadata), Qdrant (vector search), Redis (caching)
- **AI**: OpenAI API for documentation generation

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.10+
- Node.js 18+

### Backend Setup

1. Navigate to backend directory:
```bash
cd backend
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy environment file:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Set required keys (or add to .env):
```bash
export GITHUB_TOKEN=<your-github-token>  # optional for public repos, required for private repos
export NEXT_PUBLIC_API_KEY=dev-local-key
# Optional to override API url
export NEXT_PUBLIC_API_URL=http://localhost:8000
```

5. Start Docker services:
```bash
docker-compose up -d
```

5. Initialize database:
```bash
alembic upgrade head
```

6. Run the server:
```bash
uvicorn main:app --reload
```

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Run development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000)

## API Documentation

Once the backend is running:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Metrics: http://localhost:8000/metrics

## Project Structure

```
codebase-analysis-agent/
├── backend/          # FastAPI backend
│   ├── agents/       # AI agents
│   ├── api/         # API routes
│   ├── core/        # Core configuration
│   ├── models/      # Database models
│   ├── parsers/      # Code parsers
│   └── services/    # Business logic
├── frontend/         # Next.js frontend
│   ├── app/         # Next.js app router
│   ├── components/  # React components
│   └── lib/         # Utilities
└── docker-compose.yml
```

## License

MIT
