from __future__ import annotations

from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Album, Image
from src.db.schemas import AlbumSearchHit
from src.db.queries.helpers import _clean_query, _bulk_cover_ids
from src.db.queries.albums import DEFAULT_PER_PAGE


DEFAULT_SIMILARITY_THRESHOLD: float = 0.3
DEFAULT_SEARCH_LIMIT: int = 50
MIN_QUERY_LENGTH: int = 2
SUGGEST_DEFAULT_LIMIT: int = 8
SUGGEST_MIN_QUERY_LENGTH: int = 3
SUGGEST_DEFAULT_THRESHOLD: float = 0.2


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


async def search_albums_suggest(
    session: AsyncSession,
    query_str: str,
    *,
    limit: int = SUGGEST_DEFAULT_LIMIT,
    threshold: float = SUGGEST_DEFAULT_THRESHOLD,
) -> list[dict]:
    q = _clean_query(query_str)
    if not q or len(q) < SUGGEST_MIN_QUERY_LENGTH:
        logger.debug(
            f"[db.queries.search_albums_suggest] query too short (<{SUGGEST_MIN_QUERY_LENGTH}) -> [] (raw={query_str!r})"
        )
        return []

    real_limit = int(limit) if int(limit) > 0 else SUGGEST_DEFAULT_LIMIT
    real_threshold = float(threshold) if 0.0 < float(threshold) < 1.0 else SUGGEST_DEFAULT_THRESHOLD

    sim = func.similarity(Album.clean_title, q)

    top_cte = (
        select(
            Album.id.label("album_id"),
            Album.clean_title.label("clean_title"),
            sim.label("sim"),
        )
        .where(sim > real_threshold)
        .order_by(sim.desc(), Album.id.asc())
        .limit(real_limit)
        .cte("top")
    )

    img_ranked = (
        select(
            Image.album_id.label("img_album_id"),
            Image.id.label("image_id"),
            func.row_number()
            .over(
                partition_by=Image.album_id,
                order_by=(Image.is_cover.desc(), Image.position.asc(), Image.id.asc()),
            )
            .label("rn"),
        )
        .subquery("img_ranked")
    )

    stmt = (
        select(
            top_cte.c.album_id,
            top_cte.c.clean_title,
            img_ranked.c.image_id,
        )
        .select_from(top_cte)
        .join(
            img_ranked,
            and_(
                img_ranked.c.img_album_id == top_cte.c.album_id,
                img_ranked.c.rn == 1,
            ),
            isouter=True,
        )
        .order_by(top_cte.c.sim.desc(), top_cte.c.album_id.asc())
    )

    try:
        rows = (await session.execute(stmt)).all()
    except Exception as e:
        logger.exception(
            f"[db.queries.search_albums_suggest] query failed -> []: {type(e).__name__}"
        )
        return []

    out: list[dict] = []
    for aid, title, image_id in rows:
        album_id_int = int(aid)
        image_id_int = int(image_id) if image_id is not None else None
        out.append(
            {
                "id": album_id_int,
                "title": str(title or ""),
                "image_id": image_id_int,
                "url": f"/album/{album_id_int}",
            }
        )

    logger.info(
        f"[db.queries.search_albums_suggest] q={q!r} threshold={real_threshold} limit={real_limit} -> {len(out)} items"
    )
    return out


__all__ = [
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_SEARCH_LIMIT",
    "MIN_QUERY_LENGTH",
    "DEFAULT_PER_PAGE",
    "SUGGEST_DEFAULT_LIMIT",
    "SUGGEST_MIN_QUERY_LENGTH",
    "SUGGEST_DEFAULT_THRESHOLD",
    "search_albums",
    "search_albums_suggest",
]
