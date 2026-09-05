from __future__ import annotations

import argparse
import asyncio
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from loguru import logger
from sqlalchemy import or_, select

from src.core.config import get_crawl_keywords, settings
from src.db.models import Category
from src.db.session import dispose_engine, get_session_factory
from src.modules.crawler.albums_crawler import (
    AlbumsCrawler,
    CATEGORY_NAME_EXCLUDE_PATTERNS,
)
from src.services.playwright_service import PlaywrightService


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Yupoo Album Mass Crawler (keyword-filtered)")
    p.add_argument(
        "--limit-categories",
        type=int,
        default=None,
        help="For testing: only process first N categories",
    )
    p.add_argument(
        "--page-size-hint",
        type=int,
        default=120,
        help="Expected page size; stop pagination once page has fewer items",
    )
    return p.parse_args()


async def _preview_filtered_categories(limit: int | None) -> list[Category]:
    keywords = get_crawl_keywords()
    logger.info(f"Active CRAWL_KEYWORDS (upper, deduped): {keywords if keywords else '[] (ALL categories)'}")

    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Category)

        for pat in CATEGORY_NAME_EXCLUDE_PATTERNS:
            stmt = stmt.where(~Category.name.ilike(f"%{pat}%"))

        if keywords:
            include = or_(*(Category.name.ilike(f"%{kw}%") for kw in keywords))
            stmt = stmt.where(include)

        stmt = stmt.order_by(
            Category.parent_id.is_(None).desc(),
            Category.id.asc(),
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().unique().all())

    if limit is not None and len(rows) > limit:
        logger.warning(f"--limit-categories={limit}: truncating preview list from {len(rows)} to {limit}")
        rows = rows[:limit]

    logger.info(f"Filtered categories count = {len(rows)}")
    if rows:
        logger.info("Filtered category list (id, name, yupoo_path, parent_id):")
        for c in rows:
            logger.info(
                f"   #{c.id:<6} name={c.name!r:40s} path={c.yupoo_path!r:<45s} parent_id={c.parent_id!r}"
            )
    else:
        logger.warning(
            "Filtered category list is EMPTY. Check CRAWL_KEYWORDS in .env or run discovery first (scripts/run_discovery.py)."
        )

    return rows


async def main() -> int:
    args = _parse_args()
    logger.info(
        f"=== run_crawler.py: Album Mass Crawler Phase (limit_categories={args.limit_categories}, page_size_hint={args.page_size_hint}) ==="
    )
    logger.debug(
        f"Config: PROXY_URL={'ON' if settings.PROXY_URL else 'OFF'}, DB_HOST={settings.DB_HOST}, DB_PORT={settings.DB_PORT}, DB_NAME={settings.DB_NAME}"
    )

    try:
        preview_rows = await _preview_filtered_categories(args.limit_categories)
    except Exception as e:
        logger.exception(f"Can't preview categories: {type(e).__name__}: {e}")
        await dispose_engine()
        return 3

    if not preview_rows:
        logger.error("Stopping run_crawler.py because filtered categories are EMPTY.")
        await dispose_engine()
        return 2

    session_factory = get_session_factory()

    async with PlaywrightService() as browser:
        crawler = AlbumsCrawler(
            browser=browser,
            session_factory=session_factory,
            page_size_hint=args.page_size_hint,
            limit_categories=args.limit_categories,
        )
        await crawler.run()

    await dispose_engine()
    logger.success("=== run_crawler.py finished ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
