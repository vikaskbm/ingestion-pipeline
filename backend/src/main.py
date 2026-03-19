import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.annotations import router as annotations_router
from src.api.calibration import router as calibration_router
from src.api.conversations import router as conversations_router
from src.api.evaluations import router as evaluations_router
from src.api.evaluators import router as evaluators_router
from src.api.health import router as health_router
from src.api.suggestions import router as suggestions_router
from src.db.session import engine
from src.models.base import Base

import src.models  # noqa: F401

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    yield
    engine.dispose()


def _get_cors_origins() -> list[str]:
    origins = os.getenv("CORS_ORIGINS")
    if origins:
        return [o.strip() for o in origins.split(",")]
    return ["http://localhost:5173", "http://localhost:3000"]


app = FastAPI(
    title="AI Agent Evaluation Pipeline",
    version="0.1.0",
    description="API for evaluating AI agent conversations",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(conversations_router)
app.include_router(annotations_router, prefix="/conversations")
app.include_router(evaluations_router)
app.include_router(suggestions_router)
app.include_router(calibration_router)
app.include_router(evaluators_router)
