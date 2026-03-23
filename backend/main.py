import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from api.routes import (
    repositories,
    services,
    dependencies,
    impact,
    documentation,
    human_review,
    metrics,
    tech_debt
)
from core.config import get_settings
from core.database import close_neo4j_driver, init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="Codebase Analysis Agent API",
    description="AI-powered codebase analysis and dependency mapping system",
    version="1.0.0"
)

# CORS middleware — allow localhost + ip + preview URLs in dev environments.
# In production, restrict this to known origins only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
from api.middleware.rate_limit import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(
    repositories.router,
    prefix="/api/repositories",
    tags=["repositories"]
)
app.include_router(
    services.router,
    prefix="/api/services",
    tags=["services"]
)
app.include_router(
    dependencies.router,
    prefix="/api/dependencies",
    tags=["dependencies"]
)
app.include_router(
    impact.router,
    prefix="/api/impact-analysis",
    tags=["impact-analysis"]
)
app.include_router(
    documentation.router,
    prefix="/api/documentation",
    tags=["documentation"]
)
app.include_router(
    human_review.router,
    prefix="/api/human-review",
    tags=["human-review"]
)
app.include_router(
    metrics.router,
    tags=["metrics"]
)
app.include_router(
    tech_debt.router,
    prefix="/api/tech-debt",
    tags=["tech-debt"]
)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": "Codebase Analysis Agent API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "codebase-analysis-agent"
    }


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    init_db()
    logger.info("Startup complete: DB ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    close_neo4j_driver()
    logger.info("Application shutdown complete")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True
    )
