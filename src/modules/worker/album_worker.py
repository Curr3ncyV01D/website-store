from __future__ import annotations

import asyncio
import gc
import io
import os
import random
import sys
from dataclasses import dataclass
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Album, Image
from src.services.playwright_service import PlaywrightService
from src.services.telegram_service import TelegramService

MIN_IMAGE_BYTES: int = 128

IMG_URL_SELECTORS: tuple[str, ...] = (
    "img.album-detail__image",
    ".showalbum__children img.album__image",
    ".album-images img",
    ".gallery img",
    ".showalbum__main img",
    "div.showalbum__images img",
    "div.album-detail img",
    "img[data-origin-src]",
    "img[data-src]",
    "img.album__image",
    ".showalbum__parent img",
    "main img",
)

IMG_URL_ATTRS: tuple[str, ...] = (
    "data-origin-src",
    "data-src",
    "data-lazy-src",
    "data-origin",
    "src",
)


@dataclass
class WorkerStats:
    attempts: int = 0
    success_albums: int = 0
    error_albums: int = 0
    new_tg_images: int = 0
    skipped_existing_images: int = 0
    skipped_broken_images: int = 0


class AlbumWorker:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        browser: PlaywrightService,
        tg: TelegramService,
    ) -> None:
        self.session_factory: async_sessionmaker[AsyncSession] = session_factory
        self.browser: PlaywrightService = browser
        self.tg: TelegramService = tg
        self.stats = WorkerStats()

    async def get_next_pending_album(self) -> Optional[Album]:
        async with self.session_factory() as session:
            async with session.begin():
                subq = (
                    select(Album.id)
                    .where(Album.status == "pending")
                    .order_by(Album.id.asc())
                    .limit(1)
                    .with_for_update(skip_locked=True)
                    .cte("candidate")
                )
                stmt = (
                    update(Album)
                    .where(Album.id == select(subq.c.id).scalar_subquery())
                    .values(status="processing", updated_at=func.now())
                    .execution_options(synchronize_session=False)
                    .returning(Album.id)
                )
                res = await session.execute(stmt)
                row = res.fetchone()
                if row is None:
                    return None
                album_id = int(row[0])
                selected = await session.execute(
                    select(Album).where(Album.id == album_id)
                )
                album: Album | None = selected.scalar_one_or_none()
                return album

    async def _parse_image_urls(self, album_url: str) -> list[str]:
        page = self.browser._page  # noqa: SLF001
        if page is None:
            return []

        try:
            prev_y = 0
            stable_loops = 0
            for _ in range(10):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(random.uniform(0.35, 0.75))
                cur_y = await page.evaluate(
                    "() => window.scrollY || document.documentElement.scrollTop"
                )
                if cur_y == prev_y:
                    stable_loops += 1
                    if stable_loops >= 2:
                        break
                else:
                    stable_loops = 0
                prev_y = cur_y
        except Exception as e:
            logger.debug(f"[AlbumWorker] scroll issue on {album_url[:60]}: {e}")

        urls: list[str] = []
        seen: set[str] = set()
        for sel in IMG_URL_SELECTORS:
            try:
                els = await page.query_selector_all(sel)
            except Exception as e:
                logger.debug(f"[AlbumWorker] selector {sel} error: {e}")
                continue
            for el in els:
                url: Optional[str] = None
                try:
                    for attr in IMG_URL_ATTRS:
                        try:
                            v = await el.get_attribute(attr)
                        except Exception:
                            v = None
                        if v:
                            url = v
                            break
                except Exception:
                    pass
                if not url:
                    continue
                if isinstance(url, bytes):
                    try:
                        url = url.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                if url in seen:
                    continue
                if url.startswith("data:"):
                    continue
                seen.add(url)
                urls.append(url)
            if urls:
                break

        return urls

    async def _find_existing_tg_file_id(
        self, session: AsyncSession, *, album_id: int, yupoo_origin_url: str
    ) -> Optional[str]:
        q = await session.execute(
            select(Image.tg_file_id).where(
                Image.album_id == album_id,
                Image.yupoo_origin_url == yupoo_origin_url,
                Image.tg_file_id.is_not(None),
            )
        )
        row = q.fetchone()
        if row is None:
            return None
        val = row[0]
        if not val:
            return None
        return str(val)

    async def _upsert_image(
        self,
        session: AsyncSession,
        *,
        album_id: int,
        yupoo_origin_url: str,
        tg_file_id: Optional[str],
        position: int,
        is_cover: bool,
    ) -> None:
        payload = {
            "album_id": album_id,
            "yupoo_origin_url": yupoo_origin_url,
            "tg_file_id": tg_file_id,
            "position": position,
            "is_cover": is_cover,
        }

        existing_q = await session.execute(
            select(Image.id, Image.tg_file_id).where(
                Image.album_id == album_id,
                Image.yupoo_origin_url == yupoo_origin_url,
            )
        )
        existing = existing_q.fetchone()
        if existing is None:
            stmt = (
                insert(Image)
                .values(**payload)
                .on_conflict_do_nothing(
                    constraint="uq_images_album_origin",
                )
                .returning(Image.id)
            )
            r = await session.execute(stmt)
            inserted = r.fetchone()
            if inserted is not None and tg_file_id:
                logger.info(
                    f"[AlbumWorker] DB INSERT image row album_id={album_id} "
                    f"pos={position} is_cover={is_cover} tg_file_id[:24]={str(tg_file_id)[:24]!r}... "
                    f"origin={yupoo_origin_url[:70]}"
                )
            elif inserted is not None:
                logger.debug(
                    f"[AlbumWorker] DB INSERT image row album_id={album_id} pos={position} is_cover={is_cover} NO tg_file_id"
                )
            return
        _id, current_tg = existing
        if current_tg:
            update_vals = {"position": position, "is_cover": is_cover}
            await session.execute(
                update(Image).where(Image.id == _id).values(**update_vals)
            )
            logger.debug(
                f"[AlbumWorker] DB UPDATE metadata (pos/is_cover only) image_id={_id} album_id={album_id} pos={position}"
            )
            return
        update_vals = {
            "tg_file_id": tg_file_id,
            "position": position,
            "is_cover": is_cover,
        }
        await session.execute(
            update(Image).where(Image.id == _id).values(**update_vals)
        )
        if tg_file_id:
            logger.info(
                f"[AlbumWorker] DB UPDATE+SET file_id image_id={_id} album_id={album_id} "
                f"pos={position} tg_file_id[:24]={str(tg_file_id)[:24]!r}..."
            )
        else:
            logger.debug(
                f"[AlbumWorker] DB UPDATE image_id={_id} pos={position} (no tg_file_id yet)"
            )

    async def process_one_album(self, album: Album) -> None:
        self.stats.attempts += 1
        album_id: int = album.id
        album_url: str = album.yupoo_url or ""
        if not album_url:
            raise RuntimeError("Album has empty yupoo_url")

        logger.info(
            f"[AlbumWorker] START album id={album_id} url={album_url[:70]} (attempt #{self.stats.attempts})"
        )

        final_status: str = "error"
        error_reason: Optional[str] = None

        async with self.session_factory() as session:
            try:
                async with session.begin():
                    try:
                        _ = await self.browser.get_page_content(album_url)
                    except Exception as e:
                        error_reason = f"Failed to load album page: {type(e).__name__}: {e}"
                        logger.exception(f"[AlbumWorker] album id={album_id}: {error_reason}")
                        await session.execute(
                            update(Album)
                            .where(Album.id == album_id)
                            .values(status="error", updated_at=func.now())
                        )
                        self.stats.error_albums += 1
                        return

                    image_urls: list[str] = await self._parse_image_urls(album_url)
                    logger.info(
                        f"[AlbumWorker] album id={album_id}: parsed {len(image_urls)} image urls"
                    )
                    if not image_urls:
                        error_reason = "no images discovered (empty data-origin-src list)"
                        logger.error(f"[AlbumWorker] album id={album_id}: {error_reason}")
                        await session.execute(
                            update(Album)
                            .where(Album.id == album_id)
                            .values(status="error", updated_at=func.now())
                        )
                        self.stats.error_albums += 1
                        return

                    effective_total: int = len(image_urls)
                    tg_sends: int = 0
                    reused_existing: int = 0
                    broken_or_tiny: int = 0

                    for idx, raw_url in enumerate(image_urls):
                        position: int = idx
                        is_cover: bool = idx == 0
                        using_url = raw_url

                        existing_tg = await self._find_existing_tg_file_id(
                            session, album_id=album_id, yupoo_origin_url=raw_url
                        )
                        if existing_tg:
                            reused_existing += 1
                            self.stats.skipped_existing_images += 1
                            logger.info(
                                f"[AlbumWorker] album id={album_id} pos={position}: IDEMPOTENT reuse existing tg_file_id "
                                f"(skip download + TG upload), is_cover={is_cover}"
                            )
                            await self._upsert_image(
                                session,
                                album_id=album_id,
                                yupoo_origin_url=raw_url,
                                tg_file_id=existing_tg,
                                position=position,
                                is_cover=is_cover,
                            )
                            continue

                        img_bytes = b""
                        try:
                            img_bytes = await self.browser.get_image_bytes(
                                raw_url, referer=album_url
                            )
                            if not img_bytes or len(img_bytes) < MIN_IMAGE_BYTES:
                                if is_cover and album.cover_url and album.cover_url != raw_url:
                                    try:
                                        alt = await self.browser.get_image_bytes(
                                            album.cover_url, referer=album_url
                                        )
                                        if alt and len(alt) >= MIN_IMAGE_BYTES:
                                            img_bytes = alt
                                            using_url = album.cover_url
                                    except Exception:
                                        pass
                        except Exception as e:
                            logger.warning(
                                f"[AlbumWorker] album id={album_id} download img #{idx} failed: {type(e).__name__}"
                            )
                            img_bytes = b""

                        if not img_bytes or len(img_bytes) < MIN_IMAGE_BYTES:
                            broken_or_tiny += 1
                            self.stats.skipped_broken_images += 1
                            logger.warning(
                                f"[AlbumWorker] album id={album_id} skip tiny/broken img #{idx}: "
                                f"{len(img_bytes or b'')} bytes — save row without tg_file_id"
                            )
                            await self._upsert_image(
                                session,
                                album_id=album_id,
                                yupoo_origin_url=using_url,
                                tg_file_id=None,
                                position=position,
                                is_cover=is_cover,
                            )
                            continue

                        tg_file_id: Optional[str] = None
                        caption_parts: list[str] = []
                        if idx == 0:
                            if album.clean_title:
                                caption_parts.append(album.clean_title)
                            caption_parts.append(album_url)
                        caption = " | ".join([c for c in caption_parts if c])
                        try:
                            tg_file_id = await self.tg.upload_photo(
                                io.BytesIO(img_bytes), caption=caption
                            )
                            tg_sends += 1
                            self.stats.new_tg_images += 1
                            logger.info(
                                f"[AlbumWorker] Альбом {album_id}: Загружено фото {tg_sends} из {effective_total} "
                                f"(pos={position}, cover={is_cover}, reused={reused_existing}, broken={broken_or_tiny})"
                            )
                            await asyncio.sleep(random.uniform(0.5, 1.5))
                        except Exception as e:
                            error_reason = (
                                f"TG upload failed at pos {position}: {type(e).__name__}: {e}"
                            )
                            logger.exception(
                                f"[AlbumWorker] album id={album_id} TG upload #{idx} fatal: {error_reason}"
                            )
                            await session.execute(
                                update(Album)
                                .where(Album.id == album_id)
                                .values(status="error", updated_at=func.now())
                            )
                            self.stats.error_albums += 1
                            try:
                                del img_bytes
                            except Exception:
                                pass
                            return

                        await self._upsert_image(
                            session,
                            album_id=album_id,
                            yupoo_origin_url=using_url,
                            tg_file_id=tg_file_id,
                            position=position,
                            is_cover=is_cover,
                        )

                        try:
                            del img_bytes
                        except Exception:
                            pass

                    if tg_sends == 0 and reused_existing == 0:
                        error_reason = "zero successful TG uploads AND zero reused existing file_ids"
                        logger.error(
                            f"[AlbumWorker] album id={album_id}: {error_reason} "
                            f"(broken={broken_or_tiny}/{effective_total})"
                        )
                        await session.execute(
                            update(Album)
                            .where(Album.id == album_id)
                            .values(status="error", updated_at=func.now())
                        )
                        self.stats.error_albums += 1
                        return

                    await session.execute(
                        update(Album)
                        .where(Album.id == album_id)
                        .values(status="completed", updated_at=func.now())
                    )
                    final_status = "completed"
                    self.stats.success_albums += 1
                    logger.success(
                        f"[AlbumWorker] DONE album id={album_id}: "
                        f"sent_new_TG={tg_sends}, reused_file_id={reused_existing}, "
                        f"broken={broken_or_tiny}, total_urls={effective_total} -> status={final_status}"
                    )
            except Exception as top_level:
                logger.exception(
                    f"[AlbumWorker] album id={album_id}: TOP-LEVEL transaction block exception: {type(top_level).__name__}"
                )
                try:
                    await session.rollback()
                except Exception as rb:
                    logger.debug(f"[AlbumWorker] session.rollback ignored: {rb}")
                try:
                    async with session.begin():
                        await session.execute(
                            update(Album)
                            .where(Album.id == album_id)
                            .values(status="error", updated_at=func.now())
                        )
                except Exception as m:
                    logger.exception(
                        f"[AlbumWorker] album id={album_id}: FAILBACK couldn't mark status error in DB: {m}"
                    )
                self.stats.error_albums += 1
                error_reason = f"top-level exception: {type(top_level).__name__}: {top_level}"
            finally:
                try:
                    gc.collect()
                except Exception:
                    pass
                if error_reason:
                    logger.error(
                        f"[AlbumWorker] album id={album_id} FINAL STATUS error, reason: {error_reason[:200]}"
                    )
                else:
                    logger.info(
                        f"[AlbumWorker] album id={album_id} FINAL STATUS {final_status}"
                    )
