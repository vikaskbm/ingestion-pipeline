from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.db.session import engine

router = APIRouter()


@router.get("/")
def root():
    return {"message": "AI Agent Evaluation Pipeline", "docs": "/docs", "health": "/health"}


@router.get("/health")
def health_check():
    """Liveness probe: basic app responsiveness."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check():
    """Readiness probe: app + DB connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "disconnected", "error": str(e)},
        )
