from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import asyncio
import random
import urllib.parse
from dataclasses import dataclass
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import get_crawl_keywords
from src.core.security import clean_album_title
from src.db.models import Album, Category, album_category_association
from src.services.playwright_service import PlaywrightService

BASE_HOST = "https://3125tiger.x.yupoo.com"

CATEGORY_NAME_EXCLUDE_PATTERNS: tuple[str, ...] = (
    "ALL CATEGORIES",
    "ALL CATEGORY",
    "ALL ITEMS",
    "ALL PRODUCTS",
    "UNCATEGORIZED",
    "UNSORTED",
    "ДРУГОЕ",
    "ВСЕ",
    "RAZNOE",
    "OTHERS",
    "OTHER",
)

CARD_SELECTORS: tuple[str, ...] = (
    ".showalbum__children a.album__main",
    ".showalbum__children a",
    "a.album__main",
    "div.album__item > a.album__main",
    "div.showalbum__children > a",
    ".album-card a.album-link",
    ".albums-list a.album-card",
)

COVER_SELECTORS: tuple[tuple[str, str], ...] = (
    (":scope img.album__image", "src"),
    (":scope img.album-cover", "src"),
    (":scope img.cover", "src"),
    (":scope img", "src"),
    (":scope img", "data-src"),
    (":scope img", "data-lazy-src"),
    (":scope div[data-src]", "data-src"),
    (":scope div.album__cover", "style"),
)

DEFAULT_PAGE_SIZE_HINT: int = 120
PAGINATION_EMPTY_STOP: int = 2
JITTER_MIN: float = 1.5
JITTER_MAX: float = 3.5


def _urljoin(base: str, href: str) -> str:
    if not href:
        return base
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return urllib.parse.urljoin(base, href)
    return urllib.parse.urljoin(base, href)


def _extract_cover_from_style(style: str) -> Optional[str]:
    import re

    m = re.search(r"url\((?P<q>[\"']?)(?P<url>.+?)(?P=q)\)", style or "")
    if not m:
        return None
    url = m.group("url").strip()
    return url or None


@dataclass
class ParsedAlbum:
    original_title: str
    clean_title: str
    yupoo_url: str
    cover_url: Optional[str] = None


class AlbumsCrawler:
    def __init__(
        self,
        browser: PlaywrightService,
        session_factory: async_sessionmaker[AsyncSession],
        page_size_hint: int = DEFAULT_PAGE_SIZE_HINT,
        limit_categories: Optional[int] = None,
    ) -> None:
        self.browser: PlaywrightService = browser
        self.session_factory: async_sessionmaker[AsyncSession] = session_factory
        self.page_size_hint: int = page_size_hint
        self.limit_categories: Optional[int] = limit_categories

        self.stats_categories_done: int = 0
        self.stats_albums_upserted: int = 0
        self.stats_albums_new: int = 0
        self.stats_links_added: int = 0

    async def run(self) -> None:
        logger.info("[AlbumsCrawler] Starting album mass crawler")
        categories: list[Category] = await self._load_categories()
        if not categories:
            logger.error("[AlbumsCrawler] No categories found in DB. Run discovery first.")
            return

        logger.info(f"[AlbumsCrawler] Loaded {len(categories)} categories to process")

        for idx, category in enumerate(categories, start=1):
            logger.info(f"[AlbumsCrawler] === Category {idx}/{len(categories)} id={category.id} path={category.yupoo_path} ===")
            try:
                await self._crawl_one_category(category)
            except Exception as e:
                logger.exception(
                    f"[AlbumsCrawler] Category id={category.id} failed: {type(e).__name__}: {e}"
                )
            finally:
                self.stats_categories_done += 1
                await asyncio.sleep(random.uniform(1.0, 2.2))

        logger.success(
            "[AlbumsCrawler] FINAL STATS: "
            f"categories_done={self.stats_categories_done} | "
            f"albums_upserted={self.stats_albums_upserted} | "
            f"albums_new={self.stats_albums_new} | "
            f"new_category_links={self.stats_links_added}"
        )

    async def _load_categories(self) -> list[Category]:
        keywords: list[str] = get_crawl_keywords()
        async with self.session_factory() as session:
            stmt = select(Category)

            exclude_filters = [Category.name.ilike(f"%{pat}%") for pat in CATEGORY_NAME_EXCLUDE_PATTERNS]
            if exclude_filters:
                for ef in exclude_filters:
                    stmt = stmt.where(~ef)

            if keywords:
                include = or_(*(Category.name.ilike(f"%{kw}%") for kw in keywords))
                stmt = stmt.where(include)

            stmt = stmt.order_by(
                Category.parent_id.is_(None).desc(),
                Category.id.asc(),
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().unique().all())

        logger.info(
            f"[AlbumsCrawler] Filtered categories: "
            f"keywords={keywords or '(ALL, empty CRAWL_KEYWORDS)'} | matched={len(rows)}"
        )

        if self.limit_categories and len(rows) > self.limit_categories:
            logger.warning(f"[AlbumsCrawler] limit_categories={self.limit_categories}: truncating category list")
            return rows[: self.limit_categories]
        return rows

    def _build_category_page_url(self, category: Category, page: int) -> str:
        raw = category.yupoo_path or ""
        if raw.startswith("http://") or raw.startswith("https://"):
            parsed = urllib.parse.urlparse(raw)
            base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        else:
            path = raw if raw.startswith("/") else f"/{raw.lstrip('/')}"
            base = f"{BASE_HOST}{path}"

        if "?" in base:
            sep = "&"
        else:
            sep = "?"
        return f"{base}{sep}page={page}"

    async def _crawl_one_category(self, category: Category) -> None:
        page_number: int = 1
        empty_streak: int = 0

        while True:
            url = self._build_category_page_url(category, page_number)
            logger.info(f"[AlbumsCrawler]   page={page_number} -> {url}")

            try:
                await asyncio.sleep(random.uniform(JITTER_MIN, JITTER_MAX))
                html = await self.browser.get_page_content(url)
                _ = html
            except Exception as e:
                logger.exception(f"[AlbumsCrawler]   page={page_number} load failed: {type(e).__name__}: {e}")
                empty_streak += 1
                if empty_streak >= PAGINATION_EMPTY_STOP:
                    logger.info(f"[AlbumsCrawler]   category id={category.id}: {PAGINATION_EMPTY_STOP} errors in a row, stop pagination")
                    break
                page_number += 1
                continue

            page = self.browser._page  # noqa: SLF001
            parsed: list[ParsedAlbum] = []
            if page is not None:
                parsed = await self._extract_albums_from_page(page)

            if not parsed:
                logger.debug(f"[AlbumsCrawler]   page={page_number}: 0 albums parsed, fallback regex try")
                parsed = self._extract_albums_regex(url, _)

            logger.info(f"[AlbumsCrawler]   page={page_number}: {len(parsed)} albums parsed")

            if not parsed:
                empty_streak += 1
                if empty_streak >= PAGINATION_EMPTY_STOP:
                    logger.info(f"[AlbumsCrawler]   category id={category.id}: no albums for {PAGINATION_EMPTY_STOP} pages, stop")
                    break
                page_number += 1
                continue

            empty_streak = 0

            (new_albums, albums_total, links) = await self._upsert_batch(category.id, parsed)
            self.stats_albums_upserted += albums_total
            self.stats_albums_new += new_albums
            self.stats_links_added += links
            logger.info(
                f"[AlbumsCrawler]   DB: +{links} links, {albums_total} touched (+{new_albums} new)"
            )

            if len(parsed) < self.page_size_hint:
                logger.info(
                    f"[AlbumsCrawler]   page={page_number}: got {len(parsed)} < {self.page_size_hint} -> reached last page"
                )
                break
            page_number += 1

    async def _extract_albums_from_page(self, page) -> list[ParsedAlbum]:
        results: list[ParsedAlbum] = []
        seen_urls: set[str] = set()

        for selector in CARD_SELECTORS:
            try:
                elements = await page.query_selector_all(selector)
            except Exception as e:
                logger.debug(f"[AlbumsCrawler] selector {selector!r} error: {e}")
                continue
            if not elements:
                continue

            for el in elements:
                try:
                    href = (await el.get_attribute("href")) or ""
                    title_attr = (await el.get_attribute("title")) or ""
                    inner_text = (await el.inner_text()) or ""
                except Exception:
                    continue

                absolute = _urljoin(page.url, href) if hasattr(page, "url") else _urljoin(BASE_HOST, href)
                original_title = (title_attr or inner_text).strip()
                if not absolute or not original_title:
                    continue
                if absolute in seen_urls:
                    continue
                seen_urls.add(absolute)

                cover_url: Optional[str] = await self._extract_cover(el)

                clean = clean_album_title(original_title) or original_title
                results.append(
                    ParsedAlbum(
                        original_title=original_title,
                        clean_title=clean,
                        yupoo_url=absolute,
                        cover_url=cover_url,
                    )
                )

            if results:
                break
        return results

    async def _extract_cover(self, element) -> Optional[str]:
        for css, attr in COVER_SELECTORS:
            try:
                sub = await element.query_selector(css)
            except Exception:
                sub = None
            if sub is None:
                continue
            try:
                value = await sub.get_attribute(attr)
            except Exception:
                value = None
            if not value:
                continue
            if attr == "style":
                value = _extract_cover_from_style(value)
                if not value:
                    continue
            return _urljoin(BASE_HOST, value)
        return None

    def _extract_albums_regex(self, page_url: str, html: str) -> list[ParsedAlbum]:
        import re

        results: list[ParsedAlbum] = []
        seen_urls: set[str] = set()

        anchor_re = re.compile(
            r"<a\b[^>]*class=[\"'][^\"']*album__main[^\"']*[\"'][^>]*href=[\"'](?P<href>[^\"']+)[\"']"
            r"[^>]*(?:title=[\"'](?P<title>[^\"']*)[\"'])?[^>]*>(?P<body>[\s\S]*?)</a>",
            re.IGNORECASE,
        )
        img_re = re.compile(r"<img\b[^>]*\bsrc=[\"'](?P<src>[^\"']+)[\"'][^>]*>", re.IGNORECASE)
        tag_re = re.compile(r"<[^>]+>")

        for m in anchor_re.finditer(html):
            href = m.group("href") or ""
            title = (m.group("title") or "").strip()
            body = m.group("body") or ""
            if not title:
                title = tag_re.sub("", body).strip()
            if not href or not title:
                continue
            absolute = _urljoin(page_url, href)
            if absolute in seen_urls:
                continue
            seen_urls.add(absolute)

            cover_url: Optional[str] = None
            img_m = img_re.search(body)
            if img_m:
                cover_url = _urljoin(page_url, img_m.group("src"))

            clean = clean_album_title(title) or title
            results.append(
                ParsedAlbum(
                    original_title=title,
                    clean_title=clean,
                    yupoo_url=absolute,
                    cover_url=cover_url,
                )
            )
        return results

    async def _upsert_batch(
        self, category_id: int, batch: Iterable[ParsedAlbum]
    ) -> tuple[int, int, int]:
        batch_list = list(batch)
        if not batch_list:
            return 0, 0, 0

        new_albums = 0
        album_ids: list[int] = []

        async with self.session_factory() as session:
            async with session.begin():
                for pa in batch_list:
                    upsert_set = {
                        "original_title": pa.original_title,
                        "clean_title": pa.clean_title,
                    }
                    if pa.cover_url is not None:
                        upsert_set["cover_url"] = pa.cover_url

                    payload = {
                        "yupoo_url": pa.yupoo_url,
                        "original_title": pa.original_title,
                        "clean_title": pa.clean_title,
                        "cover_url": pa.cover_url,
                        "status": "pending",
                    }
                    stmt = (
                        insert(Album)
                        .values(**payload)
                        .on_conflict_do_update(
                            index_elements=[Album.yupoo_url],
                            set_=upsert_set,
                        )
                        .returning(Album.id)
                    )
                    result = await session.execute(stmt)
                    row = result.fetchone()
                    if row is None:
                        q = await session.execute(
                            select(Album.id).where(Album.yupoo_url == pa.yupoo_url)
                        )
                        album_id = q.scalar_one()
                    else:
                        album_id = int(row[0])
                    album_ids.append(album_id)

                await session.flush()

            async with session.begin():
                links_added = 0
                for album_id in album_ids:
                    lstmt = (
                        insert(album_category_association)
                        .values(album_id=album_id, category_id=category_id)
                        .on_conflict_do_nothing()
                    )
                    lres = await session.execute(lstmt)
                    if getattr(lres, "rowcount", None) and lres.rowcount and lres.rowcount > 0:
                        links_added += int(lres.rowcount)
                await session.flush()

        total_touched = len(batch_list)
        return new_albums, total_touched, links_added
