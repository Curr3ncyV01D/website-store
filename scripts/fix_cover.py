from __future__ import annotations

import asyncio
import os
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from sqlalchemy import select, update
from src.db.models import Album, Image
from src.db.session import dispose_engine, get_session_factory


def extract_yupoo_hash(url: Optional[str]) -> Optional[str]:
    """
    Извлекает уникальный хэш фотографии из ссылки Yupoo.
    Пример:
      https://photo.yupoo.com/3125tiger/a79a58be86/small.png -> 'a79a58be86'
      https://photo.yupoo.com/3125tiger/a79a58be86/fa9486d9.png -> 'a79a58be86'
    """
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path or url
        parts = [p for p in path.split("/") if p]
        # В Yupoo структура обычно: [username, hash, filename]
        if len(parts) >= 2:
            return parts[1].strip().lower()
    except Exception:
        pass
    return None


async def fix_album_covers(batch_size: int = 200):
    logger.info("=== Запуск синхронизации обложек по хэшу Yupoo ===")
    factory = get_session_factory()

    stats_total_albums = 0
    stats_matched_and_updated = 0
    stats_already_correct = 0
    stats_fallback_pos1 = 0
    stats_no_match = 0

    async with factory() as session:
        # 1. Получаем все альбомы, у которых есть скачанные изображения
        stmt = (
            select(Album)
            .order_by(Album.id.asc())
        )
        albums = (await session.execute(stmt)).scalars().all()
        stats_total_albums = len(albums)
        logger.info(f"Найдено альбомов для проверки: {stats_total_albums}")

        batch_count = 0
        for album in albums:
            # Получаем все изображения альбома, отсортированные по позиции
            img_stmt = (
                select(Image)
                .where(Image.album_id == album.id)
                .order_by(Image.position.asc())
            )
            images = (await session.execute(img_stmt)).scalars().all()

            if not images:
                continue

            target_hash = extract_yupoo_hash(album.cover_url)
            matched_image: Optional[Image] = None

            # А. Ищем совпадение по хэшу витрины
            if target_hash:
                for img in images:
                    img_hash = extract_yupoo_hash(img.yupoo_origin_url)
                    if img_hash and img_hash == target_hash:
                        matched_image = img
                        break
                    # Дополнительная проверка на вхождение хэша в URL
                    if target_hash in (img.yupoo_origin_url or "").lower():
                        matched_image = img
                        break

            # Б. Фолбэк: если хэш не найден, но фото №0 — это таблица, а фото №1 существует
            if not matched_image and len(images) > 1:
                # Если у фото №0 в ссылке есть маркеры таблицы (например 'size', 'chart')
                # или просто берем фото №1 как более безопасный вариант
                origin_0 = (images[0].yupoo_origin_url or "").lower()
                if "size" in origin_0 or "table" in origin_0 or "chart" in origin_0:
                    matched_image = images[1]
                    stats_fallback_pos1 += 1

            # Если всё еще нет совпадения — оставляем то, что было (первое фото)
            if not matched_image:
                matched_image = images[0]
                stats_no_match += 1

            # Проверяем, нужно ли обновлять базу
            current_cover_id = next((img.id for img in images if img.is_cover), None)

            if current_cover_id == matched_image.id:
                stats_already_correct += 1
            else:
                # Снимаем флаг со всех и ставим только на правильное фото
                for img in images:
                    is_this_target = (img.id == matched_image.id)
                    if img.is_cover != is_this_target:
                        img.is_cover = is_this_target

                stats_matched_and_updated += 1

            batch_count += 1
            if batch_count >= batch_size:
                await session.commit()
                batch_count = 0
                logger.debug(f"Обработано {stats_matched_and_updated + stats_already_correct}/{stats_total_albums}...")

        await session.commit()

    logger.success("=== Результаты синхронизации ===")
    logger.info(f"Всего альбомов проверено: {stats_total_albums}")
    logger.info(f"Обложек обновлено на реальное фото: {stats_matched_and_updated}")
    logger.info(f"Уже были правильными: {stats_already_correct}")
    logger.info(f"Сработало правил фолбэка: {stats_fallback_pos1}")
    logger.info(f"Оставлено по умолчанию: {stats_no_match}")

    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(fix_album_covers())