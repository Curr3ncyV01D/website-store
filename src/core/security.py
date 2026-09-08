from __future__ import annotations

import re
from typing import Final

from loguru import logger

_PRICE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"¥\s*\d+(?:[.,]\d+)?", re.IGNORECASE),
    re.compile(r"￥\s*\d+(?:[.,]\d+)?", re.IGNORECASE),
    re.compile(r"\$\s*\d+(?:[.,]\d+)?", re.IGNORECASE),
    re.compile(r"\d+(?:[.,]\d+)?\s*¥", re.IGNORECASE),
    re.compile(r"\d+(?:[.,]\d+)?\s*Y\b", re.IGNORECASE),
    re.compile(r"\d+(?:[.,]\d{2})+(?=\s|$|[^A-Za-z0-9])"),
    re.compile(r"(?<!\w)\d{2,3}[.,]\d{2}(?!\w)"),
)

_SIZE_RANGE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9])(?:XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|5XL)\s*[-–—]\s*(?:XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|5XL)(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_SINGLE_SIZE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9])(?:XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|5XL)(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_CONTACT_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\b(?:wechat|weixin|weixin\.qq|wx|vx|whatsapp|wa|watsapp|viber|telegram|tg|tel|phone|mobile|mob|cell|contact|number)\b\s*[:：#]?\s*(?:[A-Za-z0-9_\-@.+]{3,}|[+\d][\d\s\-().]{6,})", re.IGNORECASE),
    re.compile(r"(?<!\w)(?:\+\d{1,3}[\s\-()]?)?\d[\d\s\-()]{7,}\d(?!\w)"),
    re.compile(r"[:：#@]\s*[A-Za-z0-9_\-]{3,}(?=\s|$)"),
    re.compile(r"\b(?:wechat|weixin|wx|vx|whatsapp|wa|viber|telegram|tg|tel|phone|mobile|mob|cell|contact|number)\b", re.IGNORECASE),
)

_ALLOWED_CHARS_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9 \-]")
_MULTISPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s{2,}")
_MULTIHYPHEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"-{2,}")
_LEADING_TRAILING_HYPHEN: Final[re.Pattern[str]] = re.compile(r"(?:^[\s-]+|[\s-]+$)")

_HYPHEN_VARIANTS: Final[tuple[tuple[str, str], ...]] = (
    ("–", "-"),
    ("—", "-"),
    ("_", "-"),
)

_ARTIFACT_PROTECT_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:[A-Za-z]{1,6}[0-9][A-Za-z0-9]{0,6}-[A-Za-z0-9]+|[A-Za-z]{1,6}-[0-9][A-Za-z0-9]{0,6}|[A-Za-z]+\d+[A-Za-z0-9]*)\b"
)


def _apply_patterns(s: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    result = s
    for p in patterns:
        result = p.sub(" ", result)
    return result


def clean_album_title(title: str) -> str:
    if not isinstance(title, str):
        logger.warning(f"Title is not a string: {type(title).__name__}, returning empty guard")
        return title

    original = title
    working = title

    for bad, good in _HYPHEN_VARIANTS:
        working = working.replace(bad, good)

    working = _apply_patterns(working, _PRICE_PATTERNS)

    working = _SIZE_RANGE_PATTERN.sub(" ", working)
    working = _SINGLE_SIZE_PATTERN.sub(" ", working)

    # Отключено за ненадобностью пока что
    # working = _apply_patterns(working, _CONTACT_PATTERNS)

    working = _ALLOWED_CHARS_PATTERN.sub(" ", working)

    working = _MULTIHYPHEN_PATTERN.sub("-", working)
    working = _LEADING_TRAILING_HYPHEN.sub("", working)
    working = _MULTISPACE_PATTERN.sub(" ", working).strip()

    cleaned = working

    if not cleaned:
        logger.debug(f"Title cleaned to empty, falling back to original: repr={original!r}")
        fallback = original.strip()
        return fallback if fallback else original

    logger.info(f"Title cleaned: [{original}] -> [{cleaned}]")
    return cleaned
