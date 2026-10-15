from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.drawing import router as drawing_router
from app.api.game_state import router as game_state_router
from app.api.gameplay import router as gameplay_router
from app.api.rooms import router as rooms_router
from app.api.websocket import router as websocket_router
from app.api.websocket_docs import router as websocket_docs_router
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Database schema changes are handled by Alembic.
    yield


app = FastAPI(
    title=settings.app_name,
    description="Real-time multiplayer drawing and guessing game API",
    version="1.0.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(rooms_router)
app.include_router(game_state_router)
app.include_router(drawing_router)
app.include_router(gameplay_router)
app.include_router(websocket_router)
app.include_router(websocket_docs_router)


@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {"message": "Drawing Guessing Game API"}


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "healthy"}
