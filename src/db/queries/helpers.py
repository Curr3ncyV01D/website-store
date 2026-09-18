from __future__ import annotations

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Image


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


__all__ = [
    "_clean_query",
    "_first_letter",
    "_attach_covers_stmt",
    "_bulk_cover_ids",
]
