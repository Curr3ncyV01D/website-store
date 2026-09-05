from __future__ import annotations

import asyncio
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from loguru import logger

from src.db.session import dispose_engine, get_session_factory
from src.modules.crawler.categories_crawler import CategoriesCrawler
from src.services.playwright_service import PlaywrightService


async def main() -> int:
    logger.info("=== run_discovery.py: Category Discovery Phase ===")
    session_factory = get_session_factory()

    async with PlaywrightService() as browser:
        crawler = CategoriesCrawler(browser=browser, session_factory=session_factory)
        count = await crawler.run()

    await dispose_engine()
    logger.success(f"=== run_discovery.py finished. Total categories touched: {count} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
