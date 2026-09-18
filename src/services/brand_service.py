from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_recommended_brands


def top_keyword_brands() -> list[str] | None:
    """
    Рекомендуемые бренды для витрины главной страницы.

    Источник ТОЛЬКО settings.RECOMMENDED_BRANDS (конфигурация через .env).
    НЕ используем CRAWL_KEYWORDS как fallback (они технические, для crawler).

    Возвращает:
      - list[str] UPPERCASE (до 8 брендов) — если в .env явно задан список;
      - None — в остальных случаях (блок «Популярные бренды» на главной скрывается).
    """
    explicit = get_recommended_brands()
    cleaned_primary = [w for w in explicit if w and w not in {"SHOES"}]
    if cleaned_primary:
        return cleaned_primary[:8]
    return None


async def pick_brand_category_ids(
    session: AsyncSession,
    brand_names: list[str] | None,
    *,
    limit_per_brand: int = 1,
) -> list[tuple[str, int, str]]:
    """
    Для каждого бренд-имени подбираем category.id из категорий (любого уровня)
    по case-insensitive match через ILIKE.

    Правило выбора:
      * Сначала сортируем по убыванию album_count (категория с большим числом
        альбомов приоритетнее — не показываем пустые «родители» если есть
        насыщенный подкатегория).
      * Затем по имени ASC для детерминизма.
      * Дедупликация по category_id — одна категория = одна «пилюля».

    Возвращает [(brand_keyword_lookup, category_id, pretty_display_name)].
    В `pretty_display_name` — очищенное имя категории из БД (в верхнем регистре
    как в Streetwear маркетплейсе, с сохранением пробелов).
    """
    from src.db.models import Category

    out: list[tuple[str, int, str]] = []
    if not brand_names:
        return out
    seen_ids: set[int] = set()
    try:
        for brand in brand_names:
            name_like = f"%{brand}%"
            stmt = (
                select(Category.id, Category.name)
                .where(Category.name.ilike(name_like))
                .limit(limit_per_brand)
            )
            rows = (await session.execute(stmt)).all()
            for row in rows:
                cid = int(row[0])
                raw_name = row[1]
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                pretty = (str(raw_name or brand)).strip()
                pretty_upper = pretty.upper() if pretty else str(brand or "").upper()
                out.append((str(brand or "").upper(), cid, pretty_upper))
                break
    except Exception as e:
        logger.debug(f"[brand_service.pick_brand_category_ids] partial fail: {type(e).__name__}")
    return out


__all__ = [
    "top_keyword_brands",
    "pick_brand_category_ids",
]
