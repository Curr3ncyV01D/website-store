from __future__ import annotations

import asyncio
import random
import re
from pathlib import Path
import sys
from typing import Optional

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from sqlalchemy import or_, select, func, update, text
from sqlalchemy.orm import selectinload

from src.db.session import get_session_factory, dispose_engine
from src.db.models import Album, Category
from src.core.security import clean_album_title, sanitize_category_brand

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)

BATCH_SIZE = 50
HTTP_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36"
    ),
    "Referer": "https://3125tiger.x.yupoo.com/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_STORE_SUFFIX_PATTERN = re.compile(
    r"\s*\|\s*3125tiger.*|\s*\|\s*Supplier Product Catalog.*|\s*\|\s*High Quality Products.*",
    re.IGNORECASE,
)
_URL_MARKERS_PATTERN = re.compile(
    r"https?://|www\.|weidian|taobao|itemid|item\.html|item_id|\.com|\.cn|\.ru",
    re.IGNORECASE,
)
_SUSPICIOUS_CHARS_PATTERN = re.compile(
    r"[а-яА-ЯёЁ╖╜§┼╬▀╓╫╪┴┬├─│■]", re.IGNORECASE
)


def title_looks_broken(original: str, clean: str) -> bool:
    if not clean or not original:
        return True
    c = str(clean).strip()
    orig = str(original).strip()

    # 1. Слишком короткие или бессмысленные (<= 4 символов: "26 T", "T T", "2026", "1")
    if len(c) <= 4:
        return True
    if re.match(r"^\d{4}$", c):  # просто год типа 2026
        return True
    if not re.sub(r"[\W\d_]+", "", c):  # нет букв
        return True

    # 2. Содержит ссылки или мусор от магазина
    if _URL_MARKERS_PATTERN.search(c) or _URL_MARKERS_PATTERN.search(orig):
        return True
    if "3125tiger" in c.lower() or "supplier product" in c.lower():
        return True

    # 3. Содержит русские буквы/кракозябры в clean_title (чистый заголовок должен быть латиницей)
    if _SUSPICIOUS_CHARS_PATTERN.search(c):
        return True

    return False


def clean_html_tag_content(raw: str) -> str:
    if not raw:
        return ""
    s = raw.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"&nbsp;", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"&#?[A-Za-z0-9]+;", " ", s)
    s = s.replace("\u3000", " ")
    # Отрезаем системный хвост Yupoo-магазина
    s = _STORE_SUFFIX_PATTERN.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_title_from_html(html: str) -> Optional[str]:
    if not html:
        return None
    selectors = [
        re.compile(r'<h\d[^>]*class="[^"]*showalbumheader__gallerytitle[^"]*"[^>]*>(.*?)</h\d>', re.DOTALL | re.IGNORECASE),
        re.compile(r'<div[^>]*class="[^"]*showalbumheader__gallerytitle[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
        re.compile(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']', re.IGNORECASE),
        re.compile(r'<title[^>]*>(.*?)</title>', re.DOTALL | re.IGNORECASE),
    ]
    for pat in selectors:
        m = pat.search(html)
        if m:
            title = clean_html_tag_content(m.group(1))
            if title and len(title) >= 2:
                return title
    return None


async def fetch_yupoo_title(
    client: httpx.AsyncClient,
    yupoo_url: str,
    album_id: int,
) -> Optional[str]:
    if not yupoo_url:
        return None
    try:
        resp = await client.get(yupoo_url)
        if resp.status_code != 200:
            logger.warning(f"Album id={album_id}: HTTP {resp.status_code} for {yupoo_url}")
            return None
        title = extract_title_from_html(resp.text)
        return title
    except Exception as e:
        logger.warning(f"Album id={album_id}: Ошибка сети {e}")
        return None


def pick_primary_category(album: Album) -> Optional[Category]:
    if not album.categories:
        return None
    for cat in album.categories:
        if cat and (cat.name or "").strip():
            return cat
    return album.categories[0] if album.categories else None


def build_fallback_title(album: Album, category_name: Optional[str]) -> str:
    brand = sanitize_category_brand(category_name) or "Item"
    # Ищем длинный цифровой артикул
    digits = re.findall(r"\b\d{5,}\b", f"{album.clean_title} {album.original_title}")
    if digits:
        return f"{brand} {digits[0]}"
    return f"{brand} #{album.id}"


async def detect_broken_albums() -> list[Album]:
    factory = get_session_factory()
    async with factory() as session:
        # Загружаем альбомы для проверки
        stmt = select(Album).options(selectinload(Album.categories)).order_by(Album.id.asc())
        all_albums = list((await session.scalars(stmt)).unique().all())

    broken: list[Album] = []
    for a in all_albums:
        if title_looks_broken(a.original_title, a.clean_title):
            broken.append(a)
    return broken


async def process_all(limit: Optional[int] = None) -> dict:
    broken_albums = await detect_broken_albums()
    if limit:
        broken_albums = broken_albums[:limit]

    total = len(broken_albums)
    logger.info(f"Найдено поврежденных альбомов: {total}")
    if not total:
        return {"total": 0, "updated": 0, "fetched_ok": 0, "fallback_only": 0}

    updates_pending: list[dict] = []
    fetched_ok = 0
    fallback_only = 0

    transport = httpx.AsyncHTTPTransport(retries=2)
    async with httpx.AsyncClient(
        headers=HTTP_HEADERS,
        timeout=HTTP_TIMEOUT,
        transport=transport,
        trust_env=False,
        follow_redirects=True,
    ) as client:
        for idx, album in enumerate(broken_albums, start=1):
            primary_cat = pick_primary_category(album)
            category_name = primary_cat.name if primary_cat else None
            brand_clean = sanitize_category_brand(category_name)

            raw_title = await fetch_yupoo_title(client, album.yupoo_url, album.id)

            if raw_title:
                fetched_ok += 1
                # Отрезаем суффиксы магазина
                raw_title = _STORE_SUFFIX_PATTERN.sub("", raw_title).strip()
            else:
                fallback_only += 1
                raw_title = album.original_title or ""

            # Очищаем
            new_clean = clean_album_title(
                raw_title,
                category_name=brand_clean,
                album_id=album.id,
            )
            new_clean = _STORE_SUFFIX_PATTERN.sub("", new_clean).strip()

            # Если после очистки пусто или слишком коротко — формируем красивый номер
            if not new_clean or len(new_clean) <= 4 or _SUSPICIOUS_CHARS_PATTERN.search(new_clean):
                new_clean = build_fallback_title(album, category_name)

            updates_pending.append(
                {
                    "id": album.id,
                    "original_title": raw_title or album.original_title,
                    "clean_title": new_clean,
                }
            )
            logger.info(f"[{idx}/{total}] Album id={album.id} -> '{new_clean}'")

            if idx % 10 == 0:
                await asyncio.sleep(random.uniform(0.3, 0.7))

    # Сохраняем в БД батчами
    updated = 0
    factory = get_session_factory()
    for start in range(0, len(updates_pending), BATCH_SIZE):
        batch = updates_pending[start : start + BATCH_SIZE]
        async with factory() as session:
            async with session.begin():
                for row in batch:
                    await session.execute(
                        update(Album)
                        .where(Album.id == row["id"])
                        .values(
                            original_title=row["original_title"],
                            clean_title=row["clean_title"],
                        )
                    )
            updated += len(batch)

    return {
        "total": total,
        "updated": updated,
        "fetched_ok": fetched_ok,
        "fallback_only": fallback_only,
    }


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Исправление битых заголовков")
    parser.add_argument("--limit", type=int, default=None, help="Лимит альбомов")
    args = parser.parse_args()

    try:
        result = await process_all(limit=args.limit)
        print("\n============================")
        print("Итог работы fix_broken_titles.py:")
        for k, v in result.items():
            print(f"  {k:<14} = {v}")
        print("============================")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())