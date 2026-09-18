from __future__ import annotations

import math
import os
import sys
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Path as FastAPIPath, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from urllib.parse import quote as urlquote

load_dotenv()

from src.core.config import settings
from src.db.queries import (
    DEFAULT_PER_PAGE,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_SIMILARITY_THRESHOLD,
    SUGGEST_DEFAULT_LIMIT,
    SUGGEST_DEFAULT_THRESHOLD,
    AlbumDetail,
    CategoryMenuRow,
    PaginatedAlbums,
    get_album_detail,
    get_all_categories_with_counts,
    get_category_albums_paginated,
    get_category_by_id,
    get_category_path,
    get_latest_albums,
    get_latest_albums_paginated,
    search_albums,
    search_albums_suggest,
)
from src.db.schemas import BreadcrumbItem
from src.db.session import get_db_session, get_session_factory
from src.services import (
    MediaService,
    get_default_media_service,
    pick_brand_category_ids,
    top_keyword_brands,
)

PLACEHOLDER_FILENAME: str = "no-image.png"
_INFINITE_SCROLL_PER_PAGE: int = 36


async def _tpl(request: Request) -> Jinja2Templates:
    tpl: Optional[Jinja2Templates] = getattr(request.app.state, "templates", None)
    if tpl is not None:
        return tpl
    from fastapi.templating import Jinja2Templates as _Jinja2Templates

    tpl_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "templates")
    fallback = _Jinja2Templates(directory=tpl_dir)
    fallback.env.globals["settings"] = settings
    return fallback


async def _media_svc(request: Request) -> MediaService:
    svc: Optional[MediaService] = getattr(request.app.state, "media_service", None)
    if svc is None:
        svc = getattr(getattr(request.app.state, "services", None), "media", None)
    if svc is None:
        svc = get_default_media_service()
    return svc


router = APIRouter(tags=["web"])

@router.get("/favicon.ico", tags=["static"])
async def favicon(media: MediaService = Depends(_media_svc)):
    return media.favicon_response()


@router.get("/api/menu.json", tags=["api", "menu"])
async def api_menu_json(session: AsyncSession = Depends(get_db_session)) -> JSONResponse:
    rows = await get_all_categories_with_counts(session)
    payload = [
        {
            "id": r.id,
            "name": r.name,
            "album_count": r.album_count,
            "first_letter": r.first_letter,
            "url": r.url,
        }
        for r in rows
    ]
    return JSONResponse(content=jsonable_encoder(payload))


@router.get("/", response_class=HTMLResponse, tags=["pages"])
async def homepage(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    tpl: Jinja2Templates = Depends(_tpl),
):
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
            brands = await pick_brand_category_ids(session, top_keyword_brands(), limit_per_brand=1)
        except Exception as e:
            logger.exception(f"[web.router] homepage pick_brand_category_ids failed: {type(e).__name__} -> empty list")
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


@router.get("/about", response_class=HTMLResponse, tags=["pages"])
async def about_page(
    request: Request,
    tpl: Jinja2Templates = Depends(_tpl),
):
    manager_username = str(getattr(settings, "MANAGER_USERNAME", "") or "").strip().lstrip("@")
    instagram_username = str(getattr(settings, "INSTAGRAM_USERNAME", "") or "").strip().lstrip("@")
    reviews_channel_url = str(getattr(settings, "REVIEWS_CHANNEL_URL", "") or "").strip()
    context = {
        "request": request,
        "breadcrumbs": [
            {"name": "Главная", "url": "/"},
            {"name": "О проекте", "url": "/about"},
        ],
        "manager_username": manager_username,
        "telegram_manager_url": f"https://t.me/{manager_username}" if manager_username else "",
        "instagram_username": instagram_username,
        "instagram_url": f"https://instagram.com/{instagram_username}" if instagram_username else "",
        "instagram_direct_url": f"https://ig.me/m/{instagram_username}" if instagram_username else "",
        "reviews_channel_url": reviews_channel_url,
    }
    return tpl.TemplateResponse("about.html", context)


@router.get("/partial/albums", response_class=HTMLResponse, tags=["partial"])
async def partial_albums_grid(
    request: Request,
    page: int = Query(default=1, ge=1, le=100000),
    category_id: Optional[int] = Query(default=None, ge=1, le=10**9),
    session: AsyncSession = Depends(get_db_session),
    tpl: Jinja2Templates = Depends(_tpl),
):
    """
    HTMX-fragment: только HTML сетки карточек + sentinel hx-trigger=revealed следующей страницы.
    Без layout/base, без хедера/футера.

    Размер порции фиксирован (_INFINITE_SCROLL_PER_PAGE), чтобы первая страница и
    все последующие подгрузки через Infinite Scroll были согласованы.
    """
    per_page: int = _INFINITE_SCROLL_PER_PAGE
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
    tpl: Jinja2Templates = Depends(_tpl),
):

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
    tpl: Jinja2Templates = Depends(_tpl),
):
    detail: Optional[AlbumDetail] = None
    sf: async_sessionmaker[AsyncSession] = get_session_factory()
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
    instagram_username = str(getattr(settings, "INSTAGRAM_USERNAME", "") or "").strip().lstrip("@")

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

    instagram_direct_url = f"https://ig.me/m/{instagram_username}" if instagram_username else ""
    instagram_profile_url = f"https://instagram.com/{instagram_username}" if instagram_username else ""

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
        "cover_image_id": detail.cover_image_id,
        "breadcrumbs": breadcrumbs,
        "og_title": og_title,
        "og_image": og_image,
        "telegram_order_url": tg_url,
        "manager_username": manager_username_clean,
        "instagram_username": instagram_username,
        "instagram_direct_url": instagram_direct_url,
        "instagram_profile_url": instagram_profile_url,
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
    tpl: Jinja2Templates = Depends(_tpl),
):
    q_raw = (q or "").strip()
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


@router.get("/media/image/{image_id}", tags=["media"])
async def get_media_image(
    request: Request,
    image_id: int = FastAPIPath(..., ge=1),
    session: AsyncSession = Depends(get_db_session),
    media: MediaService = Depends(_media_svc),
) -> Response:
    tg_service = getattr(getattr(request.app.state, "services", None), "tg", None)
    if tg_service is None:
        tg_service = getattr(request.app.state, "tg_service", None)
    return await media.serve_image(image_id, session, tg_service)


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
