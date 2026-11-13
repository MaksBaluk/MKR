"""FastAPI entrypoint. OpenAPI: /docs; readiness uses a live SQL query."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .config import get_settings
from .db import engine
from .api import auth, catalog, profile, interviews, matches, llm, discovery, evidence, cohorts

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", description="Explainable candidate-centric MVP with curated demo fixtures")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.frontend_origins.split(",") if x.strip()],
                   allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"],
                   allow_headers=["Authorization", "Content-Type"])


@app.get("/healthz", tags=["system"])
def healthz():
    return {"status": "ok", "service": "competencematch-api"}


@app.get("/readyz", tags=["system"])
def readyz():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "Database is unavailable") from exc
    return {"status": "ready", "database": "ok"}


@app.get("/api/v1/config", tags=["system"])
def safe_config():
    return {"demo_mode": settings.demo_mode, "catalog": "local-curated-v1",
            "fixture_source": "DEMO_CURATED", "llm": llm.llm_status(),
            "parsing": "NOT_IMPLEMENTED", "esco_automatic_normalization": "NOT_IMPLEMENTED"}


for router in (auth.router, catalog.router, profile.router, discovery.router, interviews.router, evidence.router, matches.router, llm.router, cohorts.router):
    app.include_router(router, prefix="/api/v1")
