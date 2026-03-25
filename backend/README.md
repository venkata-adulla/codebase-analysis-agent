# Codebase Analysis Agent - Backend

FastAPI backend for the codebase analysis agent system.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

3. Start Docker services:
```bash
docker-compose up -d
```

4. Initialize database:
```bash
alembic upgrade head
```

5. Run the server (pick one):

```bash
# Recommended: excludes cloned repos from the file watcher so analysis does not restart the API.
python main.py
```

Or with the CLI (must exclude `repositories/` or every clone triggers `--reload` and drops clients):

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000 \
  --reload-exclude ./repositories --reload-exclude ./uploads
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Environment Variables

See `.env.example` for all available configuration options.
