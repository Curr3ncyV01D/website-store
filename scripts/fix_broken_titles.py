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
from src.db.models import Album, Category, album_category_association
from src.core.security import clean_album_title, sanitize_category_brand


logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)
logger.add(
    ROOT / "data" / "logs" / "fix_broken_titles.log",
    level="DEBUG",
    rotation="5 MB",
    retention="7 days",
    encoding="utf-8",
    delay=True,
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
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

_KRAKOZYABRA_CHARS = "╖╜ёъяфцашищж╣ёўб■§┼╬▀■╓╫╪┴┬├─│"
_URL_MARKERS_PATTERN = re.compile(
    r"http|weidian|taobao|itemid|item\.html|item_id|\.com|\.cn|\.ru",
    re.IGNORECASE,
)
_ARTIFACT_DENSITY_PATTERN = re.compile(
    r"[╖╜ёъяфцашищж╣ёўб■§┼╬▀╓╫╪┴┬├─│]+", re.IGNORECASE
)


def title_looks_broken(original: str, clean: str) -> bool:
    if original is None:
        return True
    s = str(original or "")
    stripped = s.strip()
    if len(stripped) < 4:
        return True
    if not re.sub(r"\W+", "", stripped, flags=re.UNICODE):
        return True
    if _URL_MARKERS_PATTERN.search(s):
        return True
    artifact_hits = 0
    for ch in _KRAKOZYABRA_CHARS:
        if ch in s:
            artifact_hits += 1
    if artifact_hits >= 2:
        return True
    density_matches = _ARTIFACT_DENSITY_PATTERN.findall(s)
    if sum(len(m) for m in density_matches) >= 3:
        return True
    if clean is not None:
        c_clean = str(clean or "").strip()
        if len(c_clean) < 4:
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
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_title_from_html(html: str) -> Optional[str]:
    if not html:
        return None
    selectors = [
        (re.compile(r'<h\d[^>]*class="[^"]*showalbumheader__gallerytitle[^"]*"[^>]*>(.*?)</h\d>', re.DOTALL | re.IGNORECASE), None),
        (re.compile(r'<div[^>]*class="[^"]*showalbumheader__gallerytitle[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE), None),
        (re.compile(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']', re.IGNORECASE), None),
        (re.compile(r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*property=["\']og:title["\']', re.IGNORECASE), None),
        (re.compile(r'<title[^>]*>(.*?)</title>', re.DOTALL | re.IGNORECASE), None),
    ]
    for pat, _ in selectors:
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
        logger.warning(f"Album id={album_id}: empty yupoo_url, skip HTTP fetch")
        return None
    try:
        resp = await client.get(yupoo_url)
        if resp.status_code == 404:
            logger.warning(f"Album id={album_id}: HTTP 404 for {yupoo_url}")
            return None
        if resp.status_code == 567:
            logger.warning(f"Album id={album_id}: HTTP 567 (rate-limited?) {yupoo_url}")
            return None
        if resp.status_code >= 400:
            logger.warning(f"Album id={album_id}: HTTP {resp.status_code} {yupoo_url}")
            return None
        try:
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Album id={album_id}: HTTP raise_for_status -> {e}")
            return None
        content_type = resp.headers.get("content-type", "") or ""
        charset_match = re.search(r"charset=([A-Za-z0-9\-]+)", content_type)
        if charset_match:
            html = resp.content.decode(charset_match.group(1), errors="replace")
        else:
            html = resp.text
        title = extract_title_from_html(html)
        if title:
            logger.debug(
                f"Album id={album_id}: fetched title length={len(title)} from {yupoo_url}"
            )
        return title
    except httpx.TimeoutException:
        logger.warning(f"Album id={album_id}: HTTP timeout for {yupoo_url}")
        return None
    except httpx.HTTPError as e:
        logger.warning(f"Album id={album_id}: HTTP error {type(e).__name__}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Album id={album_id}: Unexpected HTTP error: {e}")
        return None


def pick_primary_category(album: Album) -> Optional[Category]:
    if not album.categories:
        return None
    best: Optional[Category] = None
    for cat in album.categories:
        if cat is None:
            continue
        if best is None:
            best = cat
            continue
        if (cat.parent_id is None) != (best.parent_id is None):
            if cat.parent_id is None:
                continue
            best = cat
            continue
        if (cat.name or "").strip() and not (best.name or "").strip():
            best = cat
    return best


def build_fallback_title(
    *,
    album: Album,
    category_name: Optional[str],
) -> str:
    brand_sanitized = sanitize_category_brand(category_name)
    digits_match = re.search(r"\b\d{6,}\b", (album.clean_title or "") + " " + (album.original_title or ""))
    if brand_sanitized and digits_match:
        return f"{brand_sanitized} {digits_match.group(0)}".strip()
    if brand_sanitized:
        return f"{brand_sanitized} #{album.id}".strip()
    if digits_match:
        return digits_match.group(0)
    raw = (album.original_title or album.clean_title or "").strip()
    if raw and len(raw) >= 4:
        return clean_album_title(raw, category_name=category_name, album_id=album.id)
    return f"Album #{album.id}"


async def detect_broken_albums(limit: Optional[int] = None) -> list[Album]:
    factory = get_session_factory()
    async with factory() as session:
        stmt_base = select(Album).options(selectinload(Album.categories))
        total_stmt = select(func.count(Album.id))
        empty_ct = (func.coalesce(func.btrim(Album.clean_title), text("''")) == text("''"))
        short_ct = func.length(func.btrim(Album.clean_title)) < 4
        short_orig = func.length(func.btrim(Album.original_title)) < 4
        stripped_to_nothing_ct = (
            func.coalesce(
                func.btrim(
                    func.regexp_replace(Album.clean_title, r"[^\w]", "", "g")
                ),
                text("''"),
            )
            == text("''")
        )
        url_markers_ct = Album.clean_title.ilike("%http%")
        url_markers_og = Album.original_title.ilike("%http%")
        weidian_ct = or_(
            Album.clean_title.ilike("%weidian%"),
            Album.original_title.ilike("%weidian%"),
        )
        itemid_ct = or_(
            Album.clean_title.ilike("%itemid%"),
            Album.clean_title.ilike("%item.html%"),
            Album.original_title.ilike("%itemid%"),
            Album.original_title.ilike("%item.html%"),
        )
        where = or_(
            empty_ct,
            short_ct,
            short_orig,
            stripped_to_nothing_ct,
            url_markers_ct,
            url_markers_og,
            weidian_ct,
            itemid_ct,
        )
        total_where = await session.scalar(total_stmt.where(where))
        logger.info(f"БД-сигналов (OR-составной предикт): {total_where} альбомов")
        stmt = stmt_base.where(where).order_by(Album.id.asc())
        if limit:
            stmt = stmt.limit(limit)
        candidates: list[Album] = list((await session.scalars(stmt)).unique().all())
        logger.info(f"БД предикт вернул {len(candidates)} альбомов (до Python-проверки)")
    return candidates


async def process_all(limit: Optional[int] = None) -> dict:
    candidates = await detect_broken_albums(limit=limit)
    broken_albums: list[Album] = []
    for a in candidates:
        if title_looks_broken(a.original_title, a.clean_title):
            broken_albums.append(a)
    total = len(broken_albums)
    logger.info(f"Всего альбомов, признанных поврежденными (python-фильтр): {total}")
    if not total:
        return {"total": 0, "updated": 0, "fetched_ok": 0, "fallback_only": 0, "batches": 0}

    updates_pending: list[dict] = []
    fetched_ok = 0
    fallback_only = 0

    transport = httpx.AsyncHTTPTransport(retries=1)
    async with httpx.AsyncClient(
        headers=HTTP_HEADERS,
        timeout=HTTP_TIMEOUT,
        transport=transport,
        trust_env=False,
        follow_redirects=True,
    ) as client:
        for idx, album in enumerate(broken_albums, start=1):
            logger.info(
                f"[{idx}/{total}] Обработка album id={album.id} "
                f"yupoo_url={album.yupoo_url!r} orig={album.original_title[:80]!r}"
            )
            primary_cat = pick_primary_category(album)
            category_name = primary_cat.name if primary_cat else None
            raw_title = await fetch_yupoo_title(client, album.yupoo_url, album.id)
            if raw_title:
                fetched_ok += 1
            else:
                fallback_only += 1
                raw_title = album.original_title or album.clean_title or ""
                logger.debug(
                    f"Album id={album.id}: HTTP не дал заголовок, "
                    f"используем существующие данные как raw_title: {raw_title[:80]!r}"
                )
            new_clean = clean_album_title(
                raw_title,
                category_name=category_name,
                album_id=album.id,
            )
            if not new_clean or len(new_clean.strip()) < 4:
                fb = build_fallback_title(album=album, category_name=category_name)
                logger.info(
                    f"Album id={album.id}: clean_album_title дал слабый результат "
                    f"{new_clean!r}, используем fallback-title {fb!r}"
                )
                new_clean = fb
            updates_pending.append(
                {
                    "id": album.id,
                    "original_title": raw_title,
                    "clean_title": new_clean,
                    "prev_original": album.original_title,
                    "prev_clean": album.clean_title,
                }
            )
            if idx != total:
                await asyncio.sleep(random.uniform(0.2, 0.5))

    updated = 0
    batches = 0
    if updates_pending:
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
                        logger.success(
                            f"UPDATE album id={row['id']}: "
                            f"[{row['prev_original']!r} -> {row['original_title']!r}] / "
                            f"clean: [{row['prev_clean']!r} -> {row['clean_title']!r}]"
                        )
                updated += len(batch)
                batches += 1
                logger.info(
                    f"BATCH {batches}: committed {len(batch)} rows. "
                    f"Прогресс: {min(start + BATCH_SIZE, len(updates_pending))}/{len(updates_pending)}"
                )

    result = {
        "total": total,
        "updated": updated,
        "fetched_ok": fetched_ok,
        "fallback_only": fallback_only,
        "batches": batches,
    }
    logger.info(f"FINAL RESULT: {result}")
    return result


async def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Исправление поврежденных заголовков альбомов через Yupoo + fallback"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Ограничить количество обрабатываемых альбомов (для прогона на подмножестве)",
    )
    args = parser.parse_args()
    result = await process_all(limit=args.limit)
    print()
    print("============================")
    print("Итог работы fix_broken_titles.py:")
    for k, v in result.items():
        print(f"  {k:<14} = {v}")
    print("============================")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        try:
            asyncio.run(dispose_engine())
        except Exception:
            pass
