from __future__ import annotations

import os
import sys
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from src.core.config import settings
from src.db.session import dispose_engine
from src.modules.web.router import router as web_router
from src.services import TelegramService, MediaService, get_default_media_service

STATIC_DIR: Path = Path(PROJECT_ROOT) / "static"
STATIC_IMAGES_DIR: Path = STATIC_DIR / "images"
MEDIA_CACHE_DIR: Path = Path(PROJECT_ROOT) / "data" / "media_cache"
TEMPLATES_DIR: Path = Path(PROJECT_ROOT) / "templates"


@dataclass(frozen=True)
class ServiceRegistry:
    """
    Единый реестр long-lived сервисов приложения, хранящийся в `app.state.services`.

    Любой хендлер (роутер/мидлварь) читает инстансы отсюда а не держит
    собственные singleton-ы — это предотвращает дублирование движков/кэшей
    между app lifespan и @router.on_event хуками.
    """

    tg: Optional[TelegramService]
    media: MediaService


def _templates() -> Jinja2Templates:
    tpl = Jinja2Templates(directory=str(TEMPLATES_DIR))
    tpl.env.globals["settings"] = settings
    return tpl


def ensure_dirs() -> None:
    for d in (STATIC_DIR, STATIC_IMAGES_DIR, MEDIA_CACHE_DIR, TEMPLATES_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"[web] couldn't ensure dir {d}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    logger.info(
        f"[web] FastAPI lifespan startup: templates_dir={TEMPLATES_DIR}, static_dir={STATIC_DIR}, "
        f"static_images={STATIC_IMAGES_DIR}, media_cache={MEDIA_CACHE_DIR}"
    )

    # ---- Jinja templates (shared single instance) ------------------------------
    app.state.templates = _templates()

    # ---- MediaService (директории, placeholder, cache) ------------------------
    media_svc: MediaService = get_default_media_service()
    media_svc.ensure_dirs()
    await media_svc.ensure_placeholder_exists()

    # ---- TelegramService (Bot / AiohttpSession / TG CDN) ----------------------
    tg_service: Optional[TelegramService] = None
    try:
        tg_service = TelegramService()
        try:
            await tg_service.start()
            app.state.tg_service = tg_service
            logger.info(
                "[web] [TelegramService] Lifespan: singleton started OK "
                "(long-lived Bot/AiohttpSession ready)"
            )
        except Exception as e:
            logger.exception(
                f"[web] [TelegramService] Lifespan: start FAILED -> /media/image will serve placeholder fallback. "
                f"Error: {type(e).__name__}: {e}"
            )
            app.state.tg_service = None
    except Exception as e:
        logger.exception(
            f"[web] [TelegramService] Lifespan: instantiate() failed (check TG_TOKEN/TG_CHAT_ID in .env) "
            f"-> /media/image will serve placeholder. Error: {type(e).__name__}: {e}"
        )
        app.state.tg_service = None

    # ---- Registry (единая точка входа) ---------------------------------------
    app.state.services = ServiceRegistry(tg=tg_service, media=media_svc)
    app.state.media_service = media_svc  # back-compat shim

    yield  # ---------- request serving happens here ----------

    # ---- SHUTDOWN: long-lived cleanup ----------------------------------------
    if tg_service is not None:
        try:
            await tg_service.stop()
            logger.info("[web] [TelegramService] Lifespan: singleton stopped OK")
        except Exception as e:
            logger.debug(f"[web] [TelegramService] Lifespan: stop() ignored: {e}")
        finally:
            if getattr(app.state, "tg_service", None) is tg_service:
                app.state.tg_service = None

    try:
        await dispose_engine()
        logger.info("[web] SQLAlchemy engine/session_factory disposed OK")
    except Exception as e:
        logger.debug(f"[web] dispose_engine() ignored at shutdown: {e}")

    if getattr(app.state, "services", None) is not None:
        try:
            delattr(app.state, "services")
        except Exception:
            pass
    if getattr(app.state, "media_service", None) is not None:
        try:
            delattr(app.state, "media_service")
        except Exception:
            pass

    logger.info("[web] FastAPI lifespan shutdown done")


def _mount_static(app: FastAPI) -> None:
    static_dir_str = str(STATIC_DIR.resolve())
    try:
        if not STATIC_DIR.exists() or not STATIC_DIR.is_dir():
            STATIC_DIR.mkdir(parents=True, exist_ok=True)
            logger.info(f"[web] static dir {STATIC_DIR} did not exist; created")
        app.mount("/static", StaticFiles(directory=static_dir_str), name="static")
        logger.info(f"[web] mounted /static -> {static_dir_str}")
    except Exception as mount_err:
        logger.exception(f"[web] /static mount FAILED: {type(mount_err).__name__}: {mount_err}")


def create_app() -> FastAPI:
    ensure_dirs()
    app = FastAPI(
        title="Yupoo Telegram CDN Marketplace",
        description="Yupoo-parsed marketplace with Telegram-as-CDN image proxy",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.project_root = Path(PROJECT_ROOT)
    app.state.static_dir = STATIC_DIR
    app.state.static_images_dir = STATIC_IMAGES_DIR

    _mount_static(app)
    app.include_router(web_router)

    @app.get("/health", tags=["system"])
    async def health(request: Request) -> dict:
        registry = getattr(app.state, "services", None)
        return {
            "status": "ok",
            "templates_dir": str(TEMPLATES_DIR),
            "media_cache_dir": str(MEDIA_CACHE_DIR),
            "static_dir": str(STATIC_DIR),
            "static_images_dir": str(STATIC_IMAGES_DIR),
            "services": {
                "telegram_available": registry is not None and registry.tg is not None,
                "media_available": registry is not None and registry.media is not None,
            },
        }

    return app


app = create_app()
