from __future__ import annotations

import re
from typing import Final, Optional

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

_URL_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(r"www\.\S+", re.IGNORECASE),
    re.compile(r"\b[\w\-]+(?:\.(?:com|cn|ru|net|org|info|io|top|xyz|store|shop|vip|cc|co|ru|site|online|club|me))\b\S*", re.IGNORECASE),
    re.compile(r"[\w.]+/\S*item(?:\.html|/)?\S*", re.IGNORECASE),
)

_TECHNICAL_TOKENS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bweidian\b", re.IGNORECASE),
    re.compile(r"\btaobao\b", re.IGNORECASE),
    re.compile(r"\b1688\b", re.IGNORECASE),
    re.compile(r"\bitemid\b", re.IGNORECASE),
    re.compile(r"\bitem\.html\b", re.IGNORECASE),
    re.compile(r"\bitemid=\d+\b", re.IGNORECASE),
    re.compile(r"\bid=\d+\b", re.IGNORECASE),
    re.compile(r"\bspm=[A-Za-z0-9_.\-]+\b", re.IGNORECASE),
    re.compile(r"\butm_[A-Za-z_]+=\S+", re.IGNORECASE),
)

_CHINESE_CHARS_PATTERN: Final[re.Pattern[str]] = re.compile(r"[\u4e00-\u9fff]")

_CATEGORY_BRAND_STRIP_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[\s]*[\(\（][^\)\）]*[\)\）]"
)

_CLEAN_BRAND_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9 &'’\-\.]")

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

_DIGIT_SEQUENCE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b\d{6,}\b")

_MEANINGFUL_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z]{3,}"
)


def _title_is_meaningful_enough(
    cleaned: str,
    category_name: Optional[str] = None,
) -> bool:
    if not cleaned:
        return False
    s = cleaned.strip()
    if len(s) < 4:
        return False
    has_long_alpha = bool(_MEANINGFUL_TOKEN_PATTERN.search(s))
    has_skulike_digits = bool(_DIGIT_SEQUENCE_PATTERN.search(s))
    has_brand = bool(sanitize_category_brand(category_name))

    if has_long_alpha:
        return True

    if has_skulike_digits:
        if not has_brand:
            return True
        tokens = [t for t in re.split(r"\s+", s) if t]
        any_alpha_token = any(re.search(r"[A-Za-z]{2,}", t) for t in tokens)
        if any_alpha_token:
            return True
        return False

    tokens = [t for t in re.split(r"\s+", s) if t]
    alpha_tokens = [t for t in tokens if re.search(r"[A-Za-z]", t)]
    if len(alpha_tokens) >= 2 and sum(len(t) for t in alpha_tokens) >= 6:
        return True
    if has_brand and len(alpha_tokens) == 0:
        return False
    return False


def _apply_patterns(s: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    result = s
    for p in patterns:
        result = p.sub(" ", result)
    return result


def _extract_long_digits(raw_title: str, original: str) -> Optional[str]:
    for hay in (raw_title, original):
        if not hay:
            continue
        m = _DIGIT_SEQUENCE_PATTERN.search(hay)
        if m:
            return m.group(0).strip()
    return None


def sanitize_category_brand(category_name: Optional[str]) -> str:
    if not category_name:
        return ""
    s = _CATEGORY_BRAND_STRIP_PATTERN.sub(" ", str(category_name))
    s = s.strip()
    tokens = s.split()
    filtered = [t for t in tokens if t]
    cleaned = " ".join(filtered)
    cleaned = _CLEAN_BRAND_PATTERN.sub("", cleaned)
    cleaned = _MULTISPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned


def _finalize_fallback(
    *,
    cleaned_candidate: str,
    raw_title: str,
    original_title: str,
    category_name: Optional[str],
    album_id: Optional[int],
) -> str:
    digits = _extract_long_digits(raw_title, original_title)
    brand = sanitize_category_brand(category_name)

    if brand and digits:
        fb = f"{brand} {digits}".strip()
        if len(fb) >= 4:
            logger.debug(
                f"Fallback (brand+digits): brand={brand!r} digits={digits!r} -> {fb!r}"
            )
            return fb

    if brand and album_id is not None:
        fb = f"{brand} #{album_id}".strip()
        if len(fb) >= 4:
            logger.debug(
                f"Fallback (brand+id): brand={brand!r} id={album_id} -> {fb!r}"
            )
            return fb

    if digits:
        fb = digits
        if len(fb) >= 4:
            logger.debug(f"Fallback (digits only): digits={digits!r} -> {fb!r}")
            return fb

    if cleaned_candidate.strip() and len(cleaned_candidate.strip()) >= 4:
        return cleaned_candidate.strip()

    if original_title:
        sanitized = original_title
        sanitized = sanitized.replace("\x00", "")
        sanitized = _CHINESE_CHARS_PATTERN.sub(" ", sanitized)
        sanitized = _ALLOWED_CHARS_PATTERN.sub(" ", sanitized)
        sanitized = _MULTISPACE_PATTERN.sub(" ", sanitized).strip()
        if len(sanitized) >= 4:
            logger.debug(f"Fallback (sanitized original): {sanitized!r}")
            return sanitized

    if brand:
        fb = f"{brand} #{album_id}".strip() if album_id is not None else brand
        if len(fb) >= 4:
            return fb

    if cleaned_candidate.strip():
        return cleaned_candidate.strip()

    fb = original_title.strip() if original_title else (cleaned_candidate or "")
    return fb if fb else (original_title if original_title else "")


def clean_album_title(
    title: str,
    category_name: Optional[str] = None,
    album_id: Optional[int] = None,
) -> str:
    if not isinstance(title, str):
        logger.warning(f"Title is not a string: {type(title).__name__}, returning empty guard")
        if category_name or album_id is not None:
            return _finalize_fallback(
                cleaned_candidate="",
                raw_title="",
                original_title=str(title) if title else "",
                category_name=category_name,
                album_id=album_id,
            )
        return title

    original = title
    raw_title_snapshot = title
    working = title

    for bad, good in _HYPHEN_VARIANTS:
        working = working.replace(bad, good)

    working = _CHINESE_CHARS_PATTERN.sub(" ", working)

    working = _apply_patterns(working, _URL_PATTERNS)
    working = _apply_patterns(working, _TECHNICAL_TOKENS)

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

    if not _title_is_meaningful_enough(cleaned, category_name=category_name):
        logger.debug(
            f"Title not meaningful (len={len(cleaned)}, repr={cleaned!r}), entering fallback "
            f"chain. repr(original)={original!r}, category={category_name!r}, album_id={album_id}"
        )
        fb = _finalize_fallback(
            cleaned_candidate=cleaned,
            raw_title=raw_title_snapshot,
            original_title=original,
            category_name=category_name,
            album_id=album_id,
        )
        logger.info(
            f"Title fallback: [{original}] -> [{fb}] "
            f"(used_brand={bool(sanitize_category_brand(category_name))}, "
            f"used_id={album_id is not None})"
        )
        return fb

    logger.info(f"Title cleaned: [{original}] -> [{cleaned}]")
    return cleaned
