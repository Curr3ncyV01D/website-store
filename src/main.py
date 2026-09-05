from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from src.modules.web.router import router as web_router

STATIC_IMAGES_DIR: Path = Path(PROJECT_ROOT) / "static" / "images"
MEDIA_CACHE_DIR: Path = Path(PROJECT_ROOT) / "data" / "media_cache"
TEMPLATES_DIR: Path = Path(PROJECT_ROOT) / "templates"


def _templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def ensure_dirs() -> None:
    for d in (STATIC_IMAGES_DIR, MEDIA_CACHE_DIR, TEMPLATES_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"[web] couldn't ensure dir {d}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    logger.info(
        f"[web] FastAPI lifespan startup: templates_dir={TEMPLATES_DIR}, static_images={STATIC_IMAGES_DIR}, media_cache={MEDIA_CACHE_DIR}"
    )
    yield
    logger.info("[web] FastAPI lifespan shutdown")


def create_app() -> FastAPI:
    ensure_dirs()
    app = FastAPI(
        title="Yupoo Telegram CDN Marketplace",
        description="Yupoo-parsed marketplace with Telegram-as-CDN image proxy",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.templates = _templates()
    app.state.project_root = Path(PROJECT_ROOT)

    app.include_router(web_router)

    @app.get("/health", tags=["system"])
    async def health(request: Request) -> dict:
        return {
            "status": "ok",
            "templates_dir": str(TEMPLATES_DIR),
            "media_cache_dir": str(MEDIA_CACHE_DIR),
            "static_images_dir": str(STATIC_IMAGES_DIR),
        }

    return app


app = create_app()
