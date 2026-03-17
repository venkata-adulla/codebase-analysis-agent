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

5. Run the server:
```bash
uvicorn main:app --reload
```

## API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Environment Variables

See `.env.example` for all available configuration options.
