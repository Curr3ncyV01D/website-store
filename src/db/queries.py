from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Album, Category, Image, album_category_association

DEFAULT_SIMILARITY_THRESHOLD: float = 0.3
DEFAULT_SEARCH_LIMIT: int = 50
MIN_QUERY_LENGTH: int = 2
DEFAULT_PER_PAGE: int = 24


@dataclass
class AlbumSearchHit:
    album: Album
    similarity: float
    cover_image_id: Optional[int] = None
    cover_tg_file_id: Optional[str] = None


@dataclass
class AlbumCard:
    album_id: int
    clean_title: str
    cover_image_id: Optional[int]


@dataclass
class CategoryNode:
    id: int
    name: str
    yupoo_path: str
    first_letter: str = ""
    album_count: int = 0


@dataclass
class RootCategoryBranch:
    id: int
    name: str
    children: list[CategoryNode]


@dataclass
class BreadcrumbItem:
    id: Optional[int]
    name: str
    url: str


@dataclass
class PaginatedAlbums:
    items: list[AlbumCard]
    page: int
    per_page: int
    total: int
    total_pages: int
    has_prev: bool
    has_next: bool
    prev_url: Optional[str] = None
    next_url: Optional[str] = None


def _clean_query(raw: str) -> str:
    if raw is None:
        return ""
    s = str(raw).strip().strip("'\"`")
    if not s:
        return ""
    chunks = [p for p in s.split() if p]
    return " ".join(chunks)[:200]


def _first_letter(name: str) -> str:
    if not name:
        return "#"
    first = name.strip()[0]
    if first.isdigit():
        return "0–9"
    letter = first.upper()
    if not letter.isalpha() or not (("A" <= letter <= "Z") or ord(letter) > 127):
        return "#"
    return letter


def _attach_covers_stmt(album_ids: list[int]):
    if not album_ids:
        return select(Image.album_id, Image.id, Image.tg_file_id).where(False)
    cover_partition = (
        select(
            Image.album_id,
            Image.id,
            Image.tg_file_id,
            func.row_number()
            .over(
                partition_by=Image.album_id,
                order_by=(Image.is_cover.desc(), Image.position.asc(), Image.id.asc()),
            )
            .label("rn"),
        ).where(Image.album_id.in_(album_ids))
    ).subquery("cp")
    return (
        select(cover_partition.c.album_id, cover_partition.c.id, cover_partition.c.tg_file_id)
        .where(cover_partition.c.rn == 1)
    )


async def _bulk_cover_ids(session: AsyncSession, album_ids: list[int]) -> dict[int, int]:
    if not album_ids:
        return {}
    stmt = _attach_covers_stmt(album_ids)
    try:
        rows = (await session.execute(stmt)).all()
    except Exception as e:
        logger.exception(f"[db.queries._bulk_cover_ids] query failed -> empty: {type(e).__name__}")
        return {}
    out: dict[int, int] = {}
    for aid, iid, _ in rows:
        if iid is not None:
            out[int(aid)] = int(iid)
    return out


async def search_albums(
    session: AsyncSession,
    query_str: str,
    *,
    limit: int = DEFAULT_SEARCH_LIMIT,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[AlbumSearchHit]:
    q = _clean_query(query_str)
    results: list[AlbumSearchHit] = []
    if not q or len(q) < MIN_QUERY_LENGTH:
        logger.debug(
            f"[db.queries.search_albums] query too short/empty -> empty list (raw={query_str!r})"
        )
        return results

    real_limit = max(1, int(limit) if int(limit) > 0 else DEFAULT_SEARCH_LIMIT)
    real_threshold = float(threshold) if 0.0 < float(threshold) < 1.0 else DEFAULT_SIMILARITY_THRESHOLD

    sim = func.similarity(Album.clean_title, q)
    stmt = (
        select(Album, sim.label("similarity"))
        .where(sim > real_threshold)
        .order_by(sim.desc(), Album.id.asc())
        .limit(real_limit)
    )

    try:
        rows = (await session.execute(stmt)).all()
    except Exception as e:
        logger.exception(
            f"[db.queries.search_albums] session.execute failed -> empty list: {type(e).__name__}"
        )
        return results

    if not rows:
        return results

    album_ids = [int(r[0].id) for r in rows]
    covers_by_album = await _bulk_cover_ids(session, album_ids)

    for album_obj, similarity_score in rows:
        aid = int(album_obj.id)
        cover_image_id = covers_by_album.get(aid)
        results.append(
            AlbumSearchHit(
                album=album_obj,
                similarity=float(similarity_score or 0.0),
                cover_image_id=cover_image_id,
            )
        )

    logger.info(
        f"[db.queries.search_albums] q={q!r} threshold={real_threshold} limit={real_limit} -> {len(results)} rows"
    )
    return results


async def get_root_categories_with_children(
    session: AsyncSession,
) -> list[RootCategoryBranch]:
    """
    Возвращает список родительских категорий с детьми. Подсчитывает количество альбомов
    в каждой подкатегории через агрегацию по album_category_association.
    """
    out: list[RootCategoryBranch] = []
    try:
        root_rows = (await session.execute(
            select(Category)
            .where(Category.parent_id.is_(None))
            .order_by(Category.name.asc(), Category.id.asc())
        )).scalars().all()

        if not root_rows:
            return []

        sub_stmt = (
            select(
                Category.id,
                Category.name,
                Category.yupoo_path,
                Category.parent_id,
                func.count(album_category_association.c.album_id).label("album_count"),
            )
            .select_from(Category)
            .join(
                album_category_association,
                album_category_association.c.category_id == Category.id,
                isouter=True,
            )
            .where(Category.parent_id.is_not(None))
            .group_by(Category.id, Category.name, Category.yupoo_path, Category.parent_id)
        )
        sub_rows = (await session.execute(sub_stmt)).all()

        by_parent: dict[int, list[CategoryNode]] = {}
        for cid, cname, cpath, pid, cnt in sub_rows:
            node = CategoryNode(
                id=int(cid),
                name=str(cname or ""),
                yupoo_path=str(cpath or ""),
                first_letter=_first_letter(str(cname or "")),
                album_count=int(cnt or 0),
            )
            by_parent.setdefault(int(pid), []).append(node)

        for lst in by_parent.values():
            lst.sort(key=lambda x: (x.name.lower(), x.id))

        for r in root_rows:
            rid = int(r.id)
            out.append(
                RootCategoryBranch(
                    id=rid,
                    name=str(r.name or ""),
                    children=by_parent.get(rid, []),
                )
            )
        out.sort(key=lambda b: (b.name.lower(), b.id))
        logger.info(
            f"[db.queries.get_root_categories_with_children] root={len(out)} branches, total children={sum(len(b.children) for b in out)}"
        )
    except Exception as e:
        logger.exception(
            f"[db.queries.get_root_categories_with_children] failed -> empty: {type(e).__name__}"
        )
    return out


async def get_category_path(session: AsyncSession, category_id: int) -> list[BreadcrumbItem]:
    """
    Возвращает хлебные крошки Home / Parent / Subcategory
    для указанной категории (включая parents up to root).
    """
    path: list[BreadcrumbItem] = []
    try:
        current_id: Optional[int] = int(category_id)
        while current_id is not None:
            row = (await session.execute(
                select(Category.id, Category.name, Category.parent_id).where(Category.id == int(current_id)).limit(1)
            )).fetchone()
            if row is None:
                break
            cid, cname, pid = row
            path.insert(0, BreadcrumbItem(id=int(cid), name=str(cname or f"#{cid}"), url=f"/category/{int(cid)}"))
            current_id = int(pid) if pid is not None else None
    except Exception as e:
        logger.exception(f"[db.queries.get_category_path] failed for id={category_id}: {type(e).__name__}")
        return []
    return [BreadcrumbItem(id=None, name="Home", url="/")] + path


async def get_category_albums_paginated(
    session: AsyncSession,
    category_id: int,
    page: int = 1,
    per_page: int = DEFAULT_PER_PAGE,
    *,
    status_filter: Optional[str] = "completed",
) -> PaginatedAlbums:
    """
    Пагинированная выборка альбомов для категории через album_category_association.
    Возвращает Pagination DTO с items=AlbumCard (album_id, clean_title, cover_image_id).
    """
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


async def get_latest_albums(
    session: AsyncSession,
    limit: int = 24,
    *,
    status_filter: Optional[str] = "completed",
) -> list[AlbumCard]:
    """
    Главная: последние добавленные альбомы (по updated_at DESC, id DESC).
    """
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


async def get_category_by_id(session: AsyncSession, category_id: int) -> Optional[Category]:
    try:
        return (await session.execute(
            select(Category).where(Category.id == int(category_id)).limit(1)
        )).scalar_one_or_none()
    except Exception as e:
        logger.exception(f"[db.queries.get_category_by_id] failed id={category_id}: {type(e).__name__}")
        return None
