from __future__ import annotations

import os
import sys
from typing import Any, List

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Clean any stale empty CRAWL_KEYWORDS env vars set by the process (e.g., Travis/CI shells that
# export it as "=") BEFORE pydantic-settings reads them, so pydantic-settings doesn't try to
# JSON-decode a non-JSON string for list fields.
for _envkey in ("CRAWL_KEYWORDS",):
    _val = os.environ.get(_envkey)
    if _val is not None and str(_val).strip() == "":
        os.environ.pop(_envkey)

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


def _parse_keywords_csv(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        chunks = raw.split(",")
    elif isinstance(raw, (list, tuple, set)):
        chunks = [str(x) for x in raw]
    else:
        chunks = [str(raw)]
    cleaned: list[str] = []
    for v in chunks:
        piece = v.strip().strip("'\"").strip()
        if not piece:
            continue
        cleaned.append(piece.upper())
    return list(dict.fromkeys(cleaned))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "yupoo_db"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432

    PROXY_URL: str | None = None

    # NOTE: declared as `str` so pydantic-settings does NOT invoke JSON decode_complex_value()
    # (which is the problem when CRAWL_KEYWORDS appears as a raw CSV / empty env var).
    # The field_validator below converts the string (or list/tuple default override) into list[str].
    CRAWL_KEYWORDS: Any = ""

    MANAGER_USERNAME: str = "ManagerSem"
    TELEGRAM_ORDER_MESSAGE: str = 'Здравствуйте! Хочу заказать этот товар: "{title}". Ссылка: {url}'

    @field_validator("CRAWL_KEYWORDS", mode="before")
    @classmethod
    def _to_csv_list(cls, v: Any) -> Any:
        return _parse_keywords_csv(v)


settings = Settings()


def get_crawl_keywords() -> list[str]:
    value = settings.CRAWL_KEYWORDS
    if isinstance(value, list):
        return list(value)
    return _parse_keywords_csv(value)
