from __future__ import annotations

from typing import Optional, List

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Category, album_category_association
from src.db.schemas import BreadcrumbItem, CategoryMenuRow
from src.db.queries.helpers import _first_letter


async def get_category_by_id(session: AsyncSession, category_id: int) -> Optional[Category]:
    try:
        return (await session.execute(
            select(Category).where(Category.id == int(category_id)).limit(1)
        )).scalar_one_or_none()
    except Exception as e:
        logger.exception(f"[db.queries.get_category_by_id] failed id={category_id}: {type(e).__name__}")
        return None


async def get_category_path(session: AsyncSession, category_id: int) -> List[BreadcrumbItem]:
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
    return [BreadcrumbItem(id=None, name="Главная", url="/")] + path


async def get_all_categories_with_counts(
    session: AsyncSession,
) -> list[CategoryMenuRow]:
    out: list[CategoryMenuRow] = []
    try:
        stmt = (
            select(
                Category.id,
                Category.name,
                func.count(album_category_association.c.album_id).label("album_count"),
            )
            .select_from(Category)
            .join(
                album_category_association,
                album_category_association.c.category_id == Category.id,
                isouter=True,
            )
            .group_by(Category.id)
            .order_by(Category.name.asc(), Category.id.asc())
        )
        rows = (await session.execute(stmt)).all()
        for cid, cname, cnt in rows:
            name = str(cname or "").strip()
            out.append(
                CategoryMenuRow(
                    id=int(cid),
                    name=name,
                    first_letter=_first_letter(name),
                    album_count=int(cnt or 0),
                    url=f"/category/{int(cid)}",
                )
            )
        logger.info(
            f"[db.queries.get_all_categories_with_counts] total={len(out)} categories"
        )
    except Exception as e:
        logger.exception(
            f"[db.queries.get_all_categories_with_counts] failed -> empty: {type(e).__name__}"
        )
    return out


__all__ = [
    "get_category_by_id",
    "get_category_path",
    "get_all_categories_with_counts",
]
