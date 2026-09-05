from __future__ import annotations

import io
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path as StdLibPath
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Path as FastAPIPath, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import get_crawl_keywords
from src.db.models import Image
from src.db.queries import (
    DEFAULT_PER_PAGE,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SIMILARITY_THRESHOLD,
    get_category_albums_paginated,
    get_category_by_id,
    get_category_path,
    get_latest_albums,
    get_root_categories_with_children,
    search_albums,
)
from src.db.session import dispose_engine, get_db_session, get_session_factory
from src.services.telegram_service import TelegramService

PROJECT_ROOT_PATH: StdLibPath = StdLibPath(PROJECT_ROOT)
STATIC_IMAGES_DIR: StdLibPath = PROJECT_ROOT_PATH / "static" / "images"
MEDIA_CACHE_DIR: StdLibPath = PROJECT_ROOT_PATH / "data" / "media_cache"
TEMPLATES_DIR: StdLibPath = PROJECT_ROOT_PATH / "templates"

PLACEHOLDER_FILENAME: str = "no-image.png"
PLACEHOLDER_PATH: StdLibPath = STATIC_IMAGES_DIR / PLACEHOLDER_FILENAME

CACHE_CONTROL_HEADER_VALUE: str = "public, max-age=86400"
PLACEHOLDER_CACHE_CONTROL: str = "public, max-age=3600"


def _templates() -> Jinja2Templates:
    return Jinja2Templates(directory=str(TEMPLATES_DIR))


def ensure_dirs() -> None:
    for d in (STATIC_IMAGES_DIR, MEDIA_CACHE_DIR, TEMPLATES_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"[web.router] couldn't ensure dir {d}: {e}")


def _build_minimal_placeholder_png_bytes() -> bytes:
    import zlib
    import struct

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    width = 1
    height = 1
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"\x00\xaa\xaa\xaa"
    idat = zlib.compress(raw, 9)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


async def ensure_placeholder_exists() -> None:
    ensure_dirs()
    if PLACEHOLDER_PATH.exists() and PLACEHOLDER_PATH.stat().st_size > 10:
        return
    try:
        data = _build_minimal_placeholder_png_bytes()
        async with aiofiles.open(PLACEHOLDER_PATH, "wb") as f:
            await f.write(data)
        logger.info(
            f"[web.router] wrote placeholder PNG to {PLACEHOLDER_PATH} ({len(data)} bytes)"
        )
    except Exception as e:
        logger.exception(f"[web.router] FAILED to write placeholder {PLACEHOLDER_PATH}: {e}")


_TG_SINGLETON: Optional[TelegramService] = None
_TG_STARTED: bool = False


@asynccontextmanager
async def _lifespan_tg_provider():
    global _TG_SINGLETON, _TG_STARTED
    ensure_dirs()
    await ensure_placeholder_exists()
    if _TG_SINGLETON is None:
        _TG_SINGLETON = TelegramService()
    if not _TG_STARTED:
        try:
            await _TG_SINGLETON.start()
            _TG_STARTED = True
            logger.info("[web.router] TelegramService singleton started")
        except Exception as e:
            logger.exception(
                f"[web.router] TelegramService failed to start (download will use placeholder): {e}"
            )
    try:
        yield _TG_SINGLETON
    finally:
        if _TG_SINGLETON is not None and _TG_STARTED:
            try:
                await _TG_SINGLETON.stop()
            except Exception as e:
                logger.debug(f"[web.router] TelegramService stop ignored: {e}")
            finally:
                _TG_STARTED = False
                _TG_SINGLETON = None
                try:
                    await dispose_engine()
                except Exception as e:
                    logger.debug(f"[web.router] dispose_engine ignored: {e}")


@asynccontextmanager
async def request_scoped_dependencies():
    async with _lifespan_tg_provider() as tg:
        yield tg


def _cache_path_for(image_id: int) -> StdLibPath:
    return MEDIA_CACHE_DIR / f"{int(image_id)}.jpg"


router = APIRouter(tags=["web"])


@router.on_event("startup")
async def _router_startup() -> None:
    ensure_dirs()
    await ensure_placeholder_exists()


@router.get("/api/menu.json", tags=["api", "menu"])
async def api_menu_json(session: AsyncSession = Depends(get_db_session)) -> JSONResponse:
    branches = await get_root_categories_with_children(session)
    payload = [
        {
            "id": b.id,
            "name": b.name,
            "children": [
                {
                    "id": c.id,
                    "name": c.name,
                    "first_letter": c.first_letter,
                    "album_count": c.album_count,
                    "url": f"/category/{c.id}",
                }
                for c in b.children
            ],
        }
        for b in branches
    ]
    return JSONResponse(content=jsonable_encoder(payload))


def _top_keyword_brands() -> list[str]:
    words = get_crawl_keywords()
    wanted = [w for w in words if w and w not in {"SHOES"}]
    return wanted[:8] or ["ADIDAS", "NIKE", "JORDAN", "ARCTERYX", "BALENCIAGA", "RALPH LAUREN"]


async def _pick_brand_category_ids(
    session: AsyncSession,
    brand_names: list[str],
    *,
    limit_per_brand: int = 1,
) -> list[tuple[str, int, str]]:
    """
    Для каждого бренд-имени подбираем category.id из категорий (подкатегорий)
    по case-insensitive match. Возвращает [(name, category_id, category_name)].
    """
    from src.db.models import Category

    out: list[tuple[str, int, str]] = []
    seen_ids: set[int] = set()
    try:
        for brand in brand_names:
            name_like = f"%{brand}%"
            stmt = (
                select(Category.id, Category.name)
                .where(Category.parent_id.is_not(None))
                .where(func.lower(Category.name).like(func.lower(name_like)))
                .order_by(Category.name.asc(), Category.id.asc())
                .limit(limit_per_brand)
            )
            rows = (await session.execute(stmt)).all()
            for cid, cname in rows:
                if cid in seen_ids:
                    continue
                seen_ids.add(int(cid))
                out.append((brand, int(cid), str(cname or brand)))
                break
    except Exception as e:
        logger.debug(f"[web.router._pick_brand_category_ids] partial fail: {type(e).__name__}")
    return out


@router.get("/", response_class=HTMLResponse, tags=["pages"])
async def homepage(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    tpl: Jinja2Templates = getattr(request.app.state, "templates", None) or _templates()
    try:
        try:
            latest = await get_latest_albums(session, limit=24)
        except Exception as e:
            logger.exception(f"[web.router] homepage get_latest_albums failed: {type(e).__name__} -> empty list")
            latest = []
        try:
            brands = await _pick_brand_category_ids(session, _top_keyword_brands(), limit_per_brand=1)
        except Exception as e:
            logger.exception(f"[web.router] homepage _pick_brand_category_ids failed: {type(e).__name__} -> empty list")
            brands = []
    except BaseException as e:
        if "CancelledError" in type(e).__name__:
            raise
        logger.exception(f"[web.router] homepage CRITICAL: {type(e).__name__} -> graceful empty page")
        latest = []
        brands = []
    context = {
        "request": request,
        "latest_albums": latest,
        "recommended_brands": brands,
        "latest_count": len(latest),
    }
    return tpl.TemplateResponse("index.html", context)


@router.get("/category/{category_id}", response_class=HTMLResponse, tags=["pages"])
async def category_page(
    request: Request,
    category_id: int = FastAPIPath(..., ge=1),
    page: int = Query(default=1, ge=1, le=10000),
    per_page: int = Query(default=DEFAULT_PER_PAGE, ge=12, le=96),
    session: AsyncSession = Depends(get_db_session),
):
    tpl: Jinja2Templates = getattr(request.app.state, "templates", None) or _templates()

    category = None
    breadcrumbs: list = []
    pagination = None
    try:
        category = await get_category_by_id(session, category_id)
    except Exception as e:
        logger.exception(f"[web.router] /category/{category_id} get_category_by_id failed: {type(e).__name__}")
        category = None

    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    try:
        breadcrumbs = await get_category_path(session, category_id)
    except Exception as e:
        logger.exception(f"[web.router] /category/{category_id} get_category_path failed: {type(e).__name__} -> no breadcrumbs")
        breadcrumbs = [{"id": category.id, "name": category.name, "url": f"/category/{category.id}"}]

    try:
        pagination = await get_category_albums_paginated(session, category_id, page=page, per_page=per_page)
    except Exception as e:
        logger.exception(f"[web.router] /category/{category_id} get_category_albums_paginated failed: {type(e).__name__} -> empty page")
        from src.db.queries import PaginatedAlbums
        pagination = PaginatedAlbums(
            items=[], page=int(page), per_page=int(per_page), total=0,
            total_pages=1, has_prev=False, has_next=False, prev_url=None, next_url=None,
        )

    def _page_url(p: int) -> str:
        from urllib.parse import urlencode
        qp = urlencode({"page": int(p), "per_page": int(per_page)})
        return f"/category/{int(category_id)}?{qp}"

    try:
        pagination.prev_url = _page_url(pagination.page - 1) if pagination.has_prev else None
        pagination.next_url = _page_url(pagination.page + 1) if pagination.has_next else None
    except Exception:
        pass

    context = {
        "request": request,
        "category": category,
        "breadcrumbs": breadcrumbs,
        "pagination": pagination,
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "total_pages": pagination.total_pages,
        "albums": pagination.items,
        "count": len(pagination.items),
    }
    logger.info(
        f"[web.router] /category/{category_id} page={page} per={per_page} -> total={pagination.total} items={len(pagination.items)}"
    )
    return tpl.TemplateResponse("category.html", context)


@router.get("/album/{album_id}", tags=["pages (stub)"])
async def album_page_stub(
    album_id: int = FastAPIPath(..., ge=1),
) -> dict:
    return {
        "page": "album",
        "album_id": album_id,
        "status": "stub — Jinja2 gallery rendering upcoming in Phase 4",
    }


@router.get("/search", response_class=HTMLResponse, tags=["search"])
async def search_page(
    request: Request,
    q: Optional[str] = Query(default=None, min_length=0, max_length=200),
    limit: int = Query(default=DEFAULT_SEARCH_LIMIT, ge=1, le=200),
    threshold: float = Query(default=DEFAULT_SIMILARITY_THRESHOLD, gt=0.0, lt=1.0),
    session: AsyncSession = Depends(get_db_session),
):
    q_raw = (q or "").strip()
    tpl: Jinja2Templates = getattr(request.app.state, "templates", None) or _templates()
    if not q_raw:
        logger.debug("[web.router] /search called with empty 'q' -> redirect /")
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    try:
        results = await search_albums(session, q_raw, limit=limit, threshold=threshold)
    except Exception as e:
        logger.exception(f"[web.router] /search q={q_raw!r} failed: {type(e).__name__} -> empty results")
        results = []

    context: dict = {
        "request": request,
        "query": q_raw,
        "count": len(results),
        "results": results,
    }
    logger.info(
        f"[web.router] /search q={q_raw!r} -> {len(results)} hits (threshold={threshold}, limit={limit})"
    )
    return tpl.TemplateResponse("search.html", context)


def _placeholder_response(*, error_message: Optional[str] = None) -> Response:
    if PLACEHOLDER_PATH.exists():
        resp = FileResponse(
            path=PLACEHOLDER_PATH,
            media_type="image/png",
            filename=PLACEHOLDER_FILENAME,
        )
        resp.headers["Cache-Control"] = PLACEHOLDER_CACHE_CONTROL
        if error_message:
            resp.headers["X-Placeholder-Reason"] = str(error_message)[:200]
        return resp
    data = _build_minimal_placeholder_png_bytes()
    resp = Response(content=data, media_type="image/png")
    resp.headers["Cache-Control"] = PLACEHOLDER_CACHE_CONTROL
    if error_message:
        resp.headers["X-Placeholder-Reason"] = str(error_message)[:200]
    return resp


@router.get("/media/image/{image_id}", tags=["media"])
async def get_media_image(
    image_id: int = FastAPIPath(..., ge=1),
    session: AsyncSession = Depends(get_db_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> Response:
    cache_path: StdLibPath = _cache_path_for(image_id)
    if cache_path.exists():
        size = cache_path.stat().st_size
        if size > 0:
            logger.debug(
                f"[web.router] /media/image/{image_id}: serve CACHE HIT from {cache_path.name} ({size} bytes)"
            )
            resp = FileResponse(
                path=cache_path,
                media_type="image/jpeg",
                filename=f"{image_id}.jpg",
            )
            resp.headers["Cache-Control"] = CACHE_CONTROL_HEADER_VALUE
            resp.headers["X-Cache"] = "HIT"
            return resp
        try:
            cache_path.unlink(missing_ok=True)
        except Exception:
            pass

    img: Optional[Image] = None
    try:
        q = await session.execute(
            select(Image).where(Image.id == image_id).limit(1)
        )
        img = q.scalar_one_or_none()
    except Exception as e:
        logger.exception(
            f"[web.router] /media/image/{image_id}: DB select Image failed -> placeholder"
        )
        return _placeholder_response(error_message=f"db_select_error: {type(e).__name__}")

    if img is None:
        logger.warning(
            f"[web.router] /media/image/{image_id}: NOT FOUND in DB images.id -> placeholder"
        )
        return _placeholder_response(error_message="image_id_not_found")

    tg_file_id = img.tg_file_id
    if not tg_file_id:
        logger.warning(
            f"[web.router] /media/image/{image_id}: empty tg_file_id in DB (row exists but not uploaded yet) -> placeholder"
        )
        return _placeholder_response(error_message="empty_tg_file_id")

    async with request_scoped_dependencies() as tg:
        if tg is None:
            logger.error(
                f"[web.router] /media/image/{image_id}: TelegramService is unavailable -> placeholder"
            )
            return _placeholder_response(error_message="telegram_service_unavailable")
        try:
            raw_bytes: bytes = await tg.download_file(str(tg_file_id))
        except Exception as e:
            logger.exception(
                f"[web.router] /media/image/{image_id}: TelegramService download_file failed -> placeholder"
            )
            return _placeholder_response(
                error_message=f"tg_download_error: {type(e).__name__}: {str(e)[:120]}"
            )

    if not raw_bytes:
        logger.error(
            f"[web.router] /media/image/{image_id}: Telegram returned 0 bytes -> placeholder"
        )
        return _placeholder_response(error_message="tg_empty_bytes")

    # async write cache (aiofiles), keep as JPG
    try:
        async with aiofiles.open(cache_path, "wb") as f:
            await f.write(raw_bytes)
        logger.info(
            f"[web.router] /media/image/{image_id}: CACHE STORED -> {cache_path.name} ({len(raw_bytes)} bytes)"
        )
    except Exception as e:
        logger.warning(
            f"[web.router] /media/image/{image_id}: failed to write cache file {cache_path}: {e} — serving bytes from memory"
        )

    resp: Response
    if cache_path.exists() and cache_path.stat().st_size > 0:
        resp = FileResponse(
            path=cache_path,
            media_type="image/jpeg",
            filename=f"{image_id}.jpg",
        )
    else:
        resp = Response(content=raw_bytes, media_type="image/jpeg")
    resp.headers["Cache-Control"] = CACHE_CONTROL_HEADER_VALUE
    resp.headers["X-Cache"] = "MISS (from TG this time)"
    return resp
