from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import random
import urllib.parse
from dataclasses import dataclass
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Category
from src.services.playwright_service import PlaywrightService

CATEGORIES_URL = "https://3125tiger.x.yupoo.com/categories"
BASE_HOST = "https://3125tiger.x.yupoo.com"

DEFAULT_CATEGORY_SELECTORS: tuple[str, ...] = (
    "nav.categories a.category-link",
    "ul.category-list a.category-link",
    ".category-menu a",
    "aside.sidebar a.category-item",
    ".showcategory__children a.showcategory__main",
    ".categories-container a",
    ".sidebar-category a",
    "a[href*='/categories/']",
    "a[href*='/albums?categoryId']",
)

PARENT_CANDIDATE_SELECTORS: tuple[str, ...] = (
    ":scope li.category-group",
    ":scope div.category-parent",
    ":scope div.showcategory__parent",
    ":scope > ul > li",
)


@dataclass
class DiscoveredCategory:
    name: str
    yupoo_path: str
    parent_path: Optional[str] = None


def _normalize_yupoo_path(raw_path: str) -> str:
    if not raw_path:
        return ""
    if raw_path.startswith("http://") or raw_path.startswith("https://"):
        parsed = urllib.parse.urlparse(raw_path)
        raw_path = parsed.path or parsed.query or raw_path
    return raw_path.strip()


class CategoriesCrawler:
    def __init__(
        self,
        browser: PlaywrightService,
        session_factory: async_sessionmaker[AsyncSession],
        categories_url: str = CATEGORIES_URL,
    ) -> None:
        self.browser: PlaywrightService = browser
        self.session_factory: async_sessionmaker[AsyncSession] = session_factory
        self.categories_url: str = categories_url

    async def run(self) -> int:
        logger.info(f"[CategoriesCrawler] Starting discovery from {self.categories_url}")
        html: str = await self.browser.get_page_content(self.categories_url)
        logger.debug(f"[CategoriesCrawler] Categories page size: {len(html)} bytes")

        discovered: list[DiscoveredCategory] = []
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except Exception:
            pass
        page = None
        pw_instance = None
        try:
            pw_instance = __import__("playwright.async_api", fromlist=["async_playwright"]).async_playwright
            page = self.browser._page  # noqa: SLF001
        except Exception:
            page = None

        if page is not None:
            discovered = await self._extract_categories_from_page(page)

        if not discovered:
            logger.warning("[CategoriesCrawler] No categories via page. Falling back to regex HTML parse (best-effort)")
            discovered = self._extract_categories_fallback(html)

        deduped: dict[str, DiscoveredCategory] = {}
        for c in discovered:
            if not c.yupoo_path or not c.name:
                continue
            if c.yupoo_path not in deduped:
                deduped[c.yupoo_path] = c
            else:
                existing = deduped[c.yupoo_path]
                if not existing.parent_path and c.parent_path:
                    existing.parent_path = c.parent_path

        items = list(deduped.values())
        logger.info(f"[CategoriesCrawler] Discovered {len(items)} unique category entries. Upserting into DB ...")
        inserted = await self._upsert_categories(items)
        logger.success(f"[CategoriesCrawler] Done. Total DB categories touched: {inserted}")
        return inserted

    async def _extract_categories_from_page(self, page) -> list[DiscoveredCategory]:
        discovered: list[DiscoveredCategory] = []
        for selector in DEFAULT_CATEGORY_SELECTORS:
            try:
                handles = await page.query_selector_all(selector)
                if not handles:
                    continue
                logger.info(f"[CategoriesCrawler] Selector '{selector}' matched {len(handles)} anchors")
                for h in handles:
                    try:
                        raw_href = await h.get_attribute("href") or ""
                        raw_title = (
                            await h.get_attribute("title")
                            or await h.inner_text()
                            or ""
                        )
                        name = raw_title.strip()
                        path = _normalize_yupoo_path(raw_href)
                        if not path or not name:
                            continue
                        parent_path = await self._guess_parent_path(h, path)
                        discovered.append(
                            DiscoveredCategory(name=name, yupoo_path=path, parent_path=parent_path)
                        )
                    except Exception as inner:
                        logger.debug(f"[CategoriesCrawler] Skip bad link element: {inner}")
                if discovered:
                    break
            except Exception as e:
                logger.debug(f"[CategoriesCrawler] Selector '{selector}' error: {e}")
        return discovered

    async def _guess_parent_path(self, element, own_path: str) -> Optional[str]:
        for ps in PARENT_CANDIDATE_SELECTORS:
            try:
                parent_container = await element.evaluate_handle(f"el => el.closest('{ps}')")
            except Exception:
                parent_container = None
            if not parent_container:
                continue
            try:
                parent_link = await parent_container.as_element().query_selector(":scope > a")
            except Exception:
                parent_link = None
            if not parent_link:
                continue
            try:
                href = await parent_link.get_attribute("href") or ""
            except Exception:
                href = ""
            normalized = _normalize_yupoo_path(href)
            if normalized and normalized != own_path:
                return normalized
        return None

    def _extract_categories_fallback(self, html: str) -> list[DiscoveredCategory]:
        import re

        discovered: list[DiscoveredCategory] = []
        href_re = re.compile(
            r"<a\b[^>]*href=[\"'](?P<href>[^\"']*(?:/categories/|categoryId=)[^\"']*)[\"'][^>]*"
            r"(?:title=[\"'](?P<title>[^\"']*)[\"'])?[^>]*>(?P<text>[\s\S]*?)</a>",
            re.IGNORECASE,
        )
        tag_re = re.compile(r"<[^>]+>")
        for m in href_re.finditer(html):
            href = m.group("href") or ""
            title = (m.group("title") or m.group("text") or "").strip()
            title = tag_re.sub("", title).strip()
            path = _normalize_yupoo_path(href)
            if not path or not title or len(title) > 255:
                continue
            discovered.append(DiscoveredCategory(name=title, yupoo_path=path))
        return discovered

    async def _upsert_categories(
        self, items: Iterable[DiscoveredCategory]
    ) -> int:
        items_list: list[DiscoveredCategory] = list(items)
        touched: int = 0

        async with self.session_factory() as session:
            async with session.begin():
                for dc in items_list:
                    parent_id: Optional[int] = None
                    if dc.parent_path:
                        parent_q = await session.execute(
                            select(Category.id).where(Category.yupoo_path == dc.parent_path)
                        )
                        row = parent_q.scalar_one_or_none()
                        if row is not None:
                            parent_id = int(row)

                    payload = {
                        "yupoo_path": dc.yupoo_path,
                        "name": dc.name,
                        "parent_id": parent_id,
                    }
                    stmt = (
                        insert(Category)
                        .values(**payload)
                        .on_conflict_do_update(
                            index_elements=[Category.yupoo_path],
                            set_={
                                "name": payload["name"],
                                "parent_id": payload["parent_id"],
                            },
                        )
                    )
                    await session.execute(stmt)
                    touched += 1

                await session.flush()

            logger.info(f"[CategoriesCrawler] Committing {touched} category upserts ...")
        return touched
