from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, system
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    # The application intentionally starts even when DB/AI are not configured;
    # health and DB-ping endpoints make configuration problems visible.
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Read-only natural-language PostgreSQL assistant using a configurable AI provider. "
        "The AI proposes SQL but never receives database credentials or direct DB access."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

app.include_router(system.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
