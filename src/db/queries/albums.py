from __future__ import annotations

import math
from typing import Optional, List

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Album, album_category_association
from src.db.schemas import AlbumCard, AlbumDetail, BreadcrumbItem, PaginatedAlbums
from src.db.queries.helpers import _bulk_cover_ids
from src.db.queries.categories import get_category_path


DEFAULT_PER_PAGE: int = 24


async def get_album_detail(session: AsyncSession, album_id: int) -> Optional[AlbumDetail]:
    real_id = int(album_id)
    try:
        stmt = (
            select(Album)
            .options(
                selectinload(Album.images),
                selectinload(Album.categories),
            )
            .where(Album.id == real_id)
            .limit(1)
        )
        album = (await session.execute(stmt)).scalar_one_or_none()
        if album is None:
            return None

        sorted_images = sorted(
            list(album.images or []),
            key=lambda im: (int(im.position) if im.position is not None else 0, int(im.id))
        )
        images_ids: List[int] = [int(im.id) for im in sorted_images]

        cover_id: Optional[int] = None
        for im in sorted_images:
            if getattr(im, "is_cover", False):
                cover_id = int(im.id)
                break
        if cover_id is None and sorted_images:
            cover_id = int(sorted_images[0].id)

        categories_sorted = sorted(
            list(album.categories or []),
            key=lambda c: (int(c.parent_id or 0), int(c.id))
        )
        breadcrumbs: List[BreadcrumbItem] = [
            BreadcrumbItem(id=None, name="Главная", url="/"),
        ]
        if categories_sorted:
            primary_cat = categories_sorted[0]
            cat_path = (await get_category_path(session, int(primary_cat.id))) or []
            for item in cat_path:
                if item.id is None:
                    continue
                breadcrumbs.append(item)
        breadcrumbs.append(
            BreadcrumbItem(id=-int(real_id), name=str(album.clean_title or f"Товар #{real_id}"), url=f"/album/{real_id}")
        )

        return AlbumDetail(
            album_id=int(album.id),
            clean_title=str(album.clean_title or "").strip(),
            cover_image_id=cover_id,
            images=images_ids,
            breadcrumbs=breadcrumbs,
        )
    except Exception as e:
        logger.exception(f"[db.queries.get_album_detail] failed id={album_id}: {type(e).__name__}")
        return None


async def get_latest_albums(
    session: AsyncSession,
    limit: int = 24,
    *,
    status_filter: Optional[str] = "completed",
) -> list[AlbumCard]:
    real_limit = max(1, min(120, int(limit)))
    stmt = select(Album.id, Album.clean_title)
    if status_filter:
        stmt = stmt.where(Album.status == str(status_filter))
    stmt = stmt.order_by(Album.updated_at.desc(), Album.id.desc()).limit(real_limit)
    try:
        rows = (await session.execute(stmt)).all()
    except Exception as e:
        logger.exception(f"[db.queries.get_latest_albums] query failed: {type(e).__name__}")
        return []

    album_ids = [int(aid) for aid, _ in rows]
    covers = await _bulk_cover_ids(session, album_ids)
    return [
        AlbumCard(
            album_id=int(aid),
            clean_title=str(title or ""),
            cover_image_id=covers.get(int(aid)),
        )
        for aid, title in rows
    ]


async def get_latest_albums_paginated(
    session: AsyncSession,
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
    *,
    status_filter: Optional[str] = "completed",
) -> PaginatedAlbums:
    real_page = max(1, int(page))
    real_per = max(1, min(120, int(per_page)))
    offset = (real_page - 1) * real_per

    base_from = select(Album)
    if status_filter:
        base_from = base_from.where(Album.status == str(status_filter))

    count_stmt = select(func.count()).select_from(base_from)
    try:
        total = int((await session.execute(count_stmt)).scalar() or 0)
    except Exception as e:
        logger.exception(f"[db.queries.get_latest_albums_paginated] count failed: {type(e).__name__}")
        total = 0

    items: list[AlbumCard] = []
    if total > 0:
        data_stmt = select(Album.id, Album.clean_title)
        if status_filter:
            data_stmt = data_stmt.where(Album.status == str(status_filter))
        data_stmt = data_stmt.order_by(Album.updated_at.desc(), Album.id.desc()).limit(real_per).offset(offset)
        try:
            rows = (await session.execute(data_stmt)).all()
        except Exception as e:
            logger.exception(f"[db.queries.get_latest_albums_paginated] data failed: {type(e).__name__}")
            rows = []
        if rows:
            album_ids = [int(aid) for aid, _ in rows]
            covers = await _bulk_cover_ids(session, album_ids)
            items = [
                AlbumCard(
                    album_id=int(aid),
                    clean_title=str(title or ""),
                    cover_image_id=covers.get(int(aid)),
                )
                for aid, title in rows
            ]

    total_pages = max(1, math.ceil(total / real_per)) if real_per > 0 else 1
    return PaginatedAlbums(
        items=items,
        page=real_page,
        per_page=real_per,
        total=total,
        total_pages=total_pages,
        has_prev=real_page > 1,
        has_next=real_page < total_pages,
    )


async def get_category_albums_paginated(
    session: AsyncSession,
    category_id: int,
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
    *,
    status_filter: Optional[str] = "completed",
) -> PaginatedAlbums:
    real_page = max(1, int(page))
    real_per = max(1, min(96, int(per_page)))
    offset = (real_page - 1) * real_per

    base_from = (
        select(Album, func.count().over().label("total_cnt"))
        .select_from(Album)
        .join(album_category_association, album_category_association.c.album_id == Album.id)
        .where(album_category_association.c.category_id == int(category_id))
    )
    if status_filter:
        base_from = base_from.where(Album.status == str(status_filter))

    count_stmt = select(func.count()).select_from(base_from.subquery("base_count"))
    try:
        total = int((await session.execute(count_stmt)).scalar() or 0)
    except Exception as e:
        logger.exception(f"[db.queries.get_category_albums_paginated] count failed: {type(e).__name__}")
        total = 0

    items: list[AlbumCard] = []
    if total > 0:
        data_stmt = (
            select(Album.id, Album.clean_title)
            .select_from(Album)
            .join(album_category_association, album_category_association.c.album_id == Album.id)
            .where(album_category_association.c.category_id == int(category_id))
        )
        if status_filter:
            data_stmt = data_stmt.where(Album.status == str(status_filter))
        data_stmt = data_stmt.order_by(Album.updated_at.desc(), Album.id.desc()).limit(real_per).offset(offset)
        try:
            data_rows = (await session.execute(data_stmt)).all()
        except Exception as e:
            logger.exception(f"[db.queries.get_category_albums_paginated] data query failed: {type(e).__name__}")
            data_rows = []

        if data_rows:
            album_ids = [int(aid) for aid, _ in data_rows]
            covers = await _bulk_cover_ids(session, album_ids)
            items = [
                AlbumCard(
                    album_id=int(aid),
                    clean_title=str(title or ""),
                    cover_image_id=covers.get(int(aid)),
                )
                for aid, title in data_rows
            ]

    total_pages = max(1, math.ceil(total / real_per)) if real_per > 0 else 1
    has_prev = real_page > 1
    has_next = real_page < total_pages

    return PaginatedAlbums(
        items=items,
        page=real_page,
        per_page=real_per,
        total=total,
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
    )


__all__ = [
    "DEFAULT_PER_PAGE",
    "get_album_detail",
    "get_latest_albums",
    "get_latest_albums_paginated",
    "get_category_albums_paginated",
]
