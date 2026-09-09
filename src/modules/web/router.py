from __future__ import annotations

import io
import math
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path as StdLibPath
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import aiofiles
import asyncio
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Path as FastAPIPath, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from urllib.parse import quote as urlquote

load_dotenv()

from src.core.config import get_recommended_brands, settings
from src.db.models import Image
from src.db.queries import (
    DEFAULT_PER_PAGE,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SIMILARITY_THRESHOLD,
    SUGGEST_DEFAULT_LIMIT,
    SUGGEST_DEFAULT_THRESHOLD,
    AlbumDetail,
    PaginatedAlbums,
    get_album_detail,
    get_category_albums_paginated,
    get_category_by_id,
    get_category_path,
    get_latest_albums,
    get_latest_albums_paginated,
    get_root_categories_with_children,
    search_albums,
    search_albums_suggest,
)
from src.db.session import dispose_engine, get_db_session, get_session_factory

PROJECT_ROOT_PATH: StdLibPath = StdLibPath(PROJECT_ROOT)
STATIC_IMAGES_DIR: StdLibPath = PROJECT_ROOT_PATH / "static" / "images"
MEDIA_CACHE_DIR: StdLibPath = PROJECT_ROOT_PATH / "data" / "media_cache"
TEMPLATES_DIR: StdLibPath = PROJECT_ROOT_PATH / "templates"

PLACEHOLDER_FILENAME: str = "no-image.png"
PLACEHOLDER_PATH: StdLibPath = STATIC_IMAGES_DIR / PLACEHOLDER_FILENAME

FAVICON_FILENAME: str = "favicon.ico"
FAVICON_PATH: StdLibPath = STATIC_IMAGES_DIR / FAVICON_FILENAME

FAVICON_SVG_FALLBACK: str = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
    '<rect width="64" height="64" rx="12" fill="#09090b"/>'
    '<text x="50%" y="54%" text-anchor="middle" dominant-baseline="middle" '
    'font-family="Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif" '
    'font-weight="800" font-size="28" fill="#ffffff">M</text>'
    '</svg>'
)

CACHE_CONTROL_HEADER_VALUE: str = "public, max-age=86400"
PLACEHOLDER_CACHE_CONTROL: str = "public, max-age=3600"
FAVICON_CACHE_CONTROL: str = "public, max-age=7200"


def _build_database_url_for_router() -> str:
    from src.core.config import settings as _settings
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "postgres")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "yupoo_db")
    try:
        if _settings and getattr(_settings, "DB_PORT", None):
            port = str(int(getattr(_settings, "DB_PORT")))
    except Exception:
        pass
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"

_ROUTER_DB_URL = _build_database_url_for_router()
_ROUTER_ENGINE: Optional[AsyncEngine] = None
_ROUTER_SESSION_FACTORY: Optional[async_sessionmaker[AsyncSession]] = None

def _router_get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _ROUTER_ENGINE, _ROUTER_SESSION_FACTORY
    if _ROUTER_SESSION_FACTORY is None:
        _ROUTER_ENGINE = create_async_engine(
            _ROUTER_DB_URL,
            echo=False,
            future=True,
            pool_pre_ping=False,
            pool_size=5,
            max_overflow=10,
        )
        _ROUTER_SESSION_FACTORY = async_sessionmaker(
            bind=_ROUTER_ENGINE,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _ROUTER_SESSION_FACTORY


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


def _cache_path_for(image_id: int) -> StdLibPath:
    return MEDIA_CACHE_DIR / f"{int(image_id)}.jpg"


router = APIRouter(tags=["web"])


@router.on_event("startup")
async def _router_startup() -> None:
    ensure_dirs()
    await ensure_placeholder_exists()


@router.get("/favicon.ico", tags=["static"])
async def favicon():
    """
    Возвращает favicon.ico из static/images, если он есть;
    иначе — 204 No Content + SVG-fallback link (через <link rel=icon>)
    либо inline SVG-заглушка, чтобы не было 404 в консоли браузера.
    """
    try:
        if FAVICON_PATH.exists() and FAVICON_PATH.is_file() and FAVICON_PATH.stat().st_size > 0:
            resp = FileResponse(
                path=str(FAVICON_PATH),
                media_type="image/x-icon",
                filename=FAVICON_FILENAME,
            )
            resp.headers["Cache-Control"] = FAVICON_CACHE_CONTROL
            return resp
    except Exception as e:
        logger.debug(f"[web.router] /favicon.ico file open fail -> fallback: {type(e).__name__}")

    fallback_bytes = FAVICON_SVG_FALLBACK.encode("utf-8")
    resp = Response(content=fallback_bytes, media_type="image/svg+xml")
    resp.headers["Cache-Control"] = FAVICON_CACHE_CONTROL
    return resp


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


def _top_keyword_brands() -> list[str] | None:
    """
    Рекомендуемые бренды для витрины главной страницы.

    Источник ТОЛЬКО settings.RECOMMENDED_BRANDS (конфигурация через .env).
    НЕ используем CRAWL_KEYWORDS как fallback (они технические, для crawler).

    Возвращает:
      - list[str] UPPERCASE (до 8 брендов) — если в .env явно задан список;
      - None — в остальных случаях (блок «Популярные бренды» на главной скрывается).
    """
    explicit = get_recommended_brands()
    cleaned_primary = [w for w in explicit if w and w not in {"SHOES"}]
    if cleaned_primary:
        return cleaned_primary[:8]
    return None


async def _pick_brand_category_ids(
    session: AsyncSession,
    brand_names: list[str] | None,
    *,
    limit_per_brand: int = 1,
) -> list[tuple[str, int, str]]:
    """
    Для каждого бренд-имени подбираем category.id из категорий (любого уровня)
    по case-insensitive match через ILIKE.

    Правило выбора:
      * Сначала сортируем по убыванию album_count (категория с большим числом
        альбомов приоритетнее — не показываем пустые «родители» если есть
        насыщенный подкатегория).
      * Затем по имени ASC для детерминизма.
      * Дедупликация по category_id — одна категория = одна «пилюля».

    Возвращает [(brand_keyword_lookup, category_id, pretty_display_name)].
    В `pretty_display_name` — очищенное имя категории из БД (в верхнем регистре
    как в Streetwear маркетплейсе, с сохранением пробелов).
    """
    from src.db.models import Category

    out: list[tuple[str, int, str]] = []
    if not brand_names:
        return out
    seen_ids: set[int] = set()
    try:
        for brand in brand_names:
            name_like = f"%{brand}%"
            stmt = (
                select(Category.id, Category.name)
                .where(Category.name.ilike(name_like))
                .limit(limit_per_brand)
            )
            rows = (await session.execute(stmt)).all()
            for row in rows:
                cid = int(row[0])
                raw_name = row[1]
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                pretty = (str(raw_name or brand)).strip()
                pretty_upper = pretty.upper() if pretty else str(brand or "").upper()
                out.append((str(brand or "").upper(), cid, pretty_upper))
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
    latest_total = 0
    latest_total_pages = 1
    try:
        try:
            latest = await get_latest_albums(session, limit=24)
        except Exception as e:
            logger.exception(f"[web.router] homepage get_latest_albums failed: {type(e).__name__} -> empty list")
            latest = []
        try:
            from src.db.models import Album as _Album
            count_stmt = select(func.count()).select_from(_Album)
            latest_total = int((await session.execute(count_stmt)).scalar() or 0)
        except Exception as e:
            logger.debug(f"[web.router] homepage latest count fail: {type(e).__name__}")
            latest_total = len(latest)
        per_def = max(1, int(DEFAULT_PER_PAGE))
        latest_total_pages = max(1, math.ceil(max(latest_total, len(latest)) / per_def)) if per_def > 0 else 1
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
        latest_total = 0
        latest_total_pages = 1
    context = {
        "request": request,
        "latest_albums": latest,
        "recommended_brands": brands,
        "latest_count": len(latest),
        "latest_total_albums": latest_total,
        "latest_total_pages": latest_total_pages,
    }
    return tpl.TemplateResponse("index.html", context)


_INFINITE_SCROLL_PER_PAGE: int = 36


@router.get("/partial/albums", response_class=HTMLResponse, tags=["partial"])
async def partial_albums_grid(
    request: Request,
    page: int = Query(default=1, ge=1, le=100000),
    category_id: Optional[int] = Query(default=None, ge=1, le=10**9),
    session: AsyncSession = Depends(get_db_session),
):
    """
    HTMX-fragment: только HTML сетки карточек + sentinel hx-trigger=revealed следующей страницы.
    Без layout/base, без хедера/футера.

    Размер порции фиксирован (_INFINITE_SCROLL_PER_PAGE), чтобы первая страница и
    все последующие подгрузки через Infinite Scroll были согласованы.
    """
    per_page: int = _INFINITE_SCROLL_PER_PAGE
    tpl: Jinja2Templates = getattr(request.app.state, "templates", None) or _templates()
    pagination: Optional[PaginatedAlbums] = None
    try:
        if category_id is None:
            pagination = await get_latest_albums_paginated(session, page=page, per_page=per_page)
        else:
            cat = await get_category_by_id(session, category_id)
            if cat is None:
                pagination = PaginatedAlbums(items=[], page=page, per_page=per_page, total=0, total_pages=1, has_prev=False, has_next=False)
            else:
                pagination = await get_category_albums_paginated(session, category_id, page=page, per_page=per_page)
    except BaseException as e:
        if "CancelledError" in type(e).__name__:
            raise
        logger.exception(f"[web.router] /partial/albums page={page} category_id={category_id}: {type(e).__name__}")
        pagination = PaginatedAlbums(items=[], page=page, per_page=per_page, total=0, total_pages=1, has_prev=False, has_next=False)

    next_url_parts = [f"/partial/albums?page={int(page) + 1}&per_page={int(per_page)}"]
    if category_id is not None:
        next_url_parts[0] += f"&category_id={int(category_id)}"
    next_url = next_url_parts[0]

    albums = list(pagination.items or [])
    ctx = {
        "request": request,
        "page": int(page),
        "albums": albums,
        "has_next": bool(getattr(pagination, "has_next", False)),
        "next_url": next_url,
    }
    resp = tpl.TemplateResponse("components/album_grid_chunk.html", ctx)
    try:
        resp.headers["Cache-Control"] = "private, no-store, max-age=0"
    except Exception:
        pass
    return resp


@router.get("/category/{category_id}", response_class=HTMLResponse, tags=["pages"])
async def category_page(
    request: Request,
    category_id: int = FastAPIPath(..., ge=1),
    page: int = Query(default=1, ge=1, le=10000),
    session: AsyncSession = Depends(get_db_session),
):
    tpl: Jinja2Templates = getattr(request.app.state, "templates", None) or _templates()

    per_page: int = _INFINITE_SCROLL_PER_PAGE
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

    context = {
        "request": request,
        "category": category,
        "breadcrumbs": breadcrumbs,
        "pagination": pagination,
        "page": pagination.page,
        "total": pagination.total,
        "albums": pagination.items,
        "count": len(pagination.items),
    }
    logger.info(
        f"[web.router] /category/{category_id} page={page} per={per_page} -> total={pagination.total} items={len(pagination.items)}"
    )
    return tpl.TemplateResponse("category.html", context)


@router.get("/album/{album_id}", response_class=HTMLResponse, tags=["pages"])
async def album_page(
    request: Request,
    album_id: int = FastAPIPath(..., ge=1),
):
    tpl: Jinja2Templates = getattr(request.app.state, "templates", None) or _templates()
    detail: Optional[AlbumDetail] = None
    sf: async_sessionmaker[AsyncSession] = _router_get_session_factory()
    async with sf() as s2:
        try:
            detail = await get_album_detail(s2, album_id)
        except BaseException as be:
            if isinstance(be, (TimeoutError, ConnectionError, asyncio.CancelledError)):
                detail = None
            else:
                logger.exception(
                    f"[web.router] /album/{album_id} get_album_detail raised {type(be).__name__}: {be}"
                )
                detail = None
    if detail is None or not detail.clean_title:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Reseller Protection:
    # NEVER pass original_title or weidian_url into template context.
    og_title = detail.clean_title or "Товар"
    og_image = f"/media/image/{detail.cover_image_id}" if detail.cover_image_id else f"/static/images/{PLACEHOLDER_FILENAME}"

    manager_username = str(getattr(settings, "MANAGER_USERNAME", "") or "").strip()
    manager_username_clean = manager_username.lstrip("@")

    tpl_msg = str(getattr(settings, "TELEGRAM_ORDER_MESSAGE", "") or "").strip()
    if not tpl_msg:
        tpl_msg = 'Здравствуйте! Хочу заказать этот товар: "{title}". Ссылка: {url}'

    try:
        current_url = str(request.url)
    except Exception:
        current_url = f"/album/{detail.album_id}"
    try:
        prefill_text = tpl_msg.format(title=detail.clean_title, url=current_url)
    except Exception:
        prefill_text = f'Здравствуйте! Хочу заказать этот товар: "{detail.clean_title}". Ссылка: {current_url}'
    try:
        tg_url = f"https://t.me/{manager_username_clean}?text={urlquote(prefill_text, safe='')}"
    except Exception:
        tg_url = f"https://t.me/{manager_username_clean}"

    # breadcrumbs: keep Главная/Категория/Товар as expected; last one is plain text, not link
    breadcrumbs = list(detail.breadcrumbs or [])
    if not breadcrumbs or breadcrumbs[0].name != "Главная":
        breadcrumbs = [BreadcrumbItem(id=None, name="Главная", url="/")] + breadcrumbs

    context: dict = {
        "request": request,
        "album": detail,
        "album_id": detail.album_id,
        "title": detail.clean_title,
        "images": detail.images,
        "breadcrumbs": breadcrumbs,
        "og_title": og_title,
        "og_image": og_image,
        "telegram_order_url": tg_url,
    }
    logger.info(f"[web.router] /album/{detail.album_id} detail rendered ({len(detail.images or [])} images)")
    return tpl.TemplateResponse("album.html", context)


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
        )
        resp.headers["Content-Disposition"] = "inline"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = PLACEHOLDER_CACHE_CONTROL
        if error_message:
            resp.headers["X-Placeholder-Reason"] = str(error_message)[:200]
        return resp
    data = _build_minimal_placeholder_png_bytes()
    resp = Response(content=data, media_type="image/png")
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = PLACEHOLDER_CACHE_CONTROL
    if error_message:
        resp.headers["X-Placeholder-Reason"] = str(error_message)[:200]
    return resp


@router.get("/media/image/{image_id}", tags=["media"])
async def get_media_image(
    request: Request,
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
            )
            # Explicitly inline = never trigger Save-As dialog; browsers render inline.
            resp.headers["Content-Disposition"] = "inline"
            resp.headers["X-Content-Type-Options"] = "nosniff"
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

    tg_service = getattr(getattr(request, "app", None), "state", None)
    tg = None
    if tg_service is not None:
        tg = getattr(tg_service, "tg_service", None)

    if tg is None:
        logger.error(
            f"[web.router] /media/image/{image_id}: TelegramService singleton MISSING in app.state "
            f"(lifespan failed or TG_TOKEN/TG_CHAT_ID wrong? check startup logs) -> placeholder"
        )
        return _placeholder_response(error_message="tg_service_missing_in_app_state")

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
        )
    else:
        resp = Response(content=raw_bytes, media_type="image/jpeg")
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Cache-Control"] = CACHE_CONTROL_HEADER_VALUE
    resp.headers["X-Cache"] = "MISS (from TG this time)"
    return resp


@router.get("/api/search/suggest", tags=["api", "search"])
async def api_search_suggest(
    q: Optional[str] = Query(default=None, min_length=0, max_length=200),
    limit: int = Query(default=SUGGEST_DEFAULT_LIMIT, ge=1, le=50),
    threshold: float = Query(default=SUGGEST_DEFAULT_THRESHOLD, gt=0.0, lt=1.0),
    session: AsyncSession = Depends(get_db_session),
):
    q_raw = (q or "").strip()
    if not q_raw or len(q_raw) < 3:
        return JSONResponse(content=[], status_code=status.HTTP_200_OK)

    try:
        results = await search_albums_suggest(
            session, q_raw, limit=limit, threshold=threshold
        )
    except BaseException as e:
        if "CancelledError" in type(e).__name__:
            raise
        logger.exception(
            f"[web.router] /api/search/suggest q={q_raw!r} FAIL -> empty: {type(e).__name__}"
        )
        results = []

    payload: list = []
    try:
        for r in results:
            try:
                if isinstance(r, dict):
                    payload.append(
                        {
                            "id": int(r["id"]),
                            "title": str(r.get("title") or ""),
                            "image_id": (int(r["image_id"]) if r.get("image_id") is not None else None),
                            "url": str(r.get("url") or f"/album/{int(r['id'])}"),
                        }
                    )
                else:
                    payload.append(jsonable_encoder(r))
            except Exception as row_err:
                logger.warning(
                    f"[web.router] /api/search/suggest skip bad row {r!r}: {row_err}"
                )
    except Exception as e:
        logger.exception(
            f"[web.router] /api/search/suggest payload encode failed -> []: {type(e).__name__}"
        )
        payload = []

    return JSONResponse(content=payload, status_code=status.HTTP_200_OK)
