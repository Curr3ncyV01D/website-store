from __future__ import annotations

import asyncio
import gc
import io
import os
import sys
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import BufferedInputFile, Message
from aiohttp import ClientTimeout, ClientError

DEFAULT_BOT_TOKEN_ENV: str = "TG_TOKEN"
DEFAULT_CHAT_ID_ENV: str = "TG_CHAT_ID"
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_BACKOFF_BASE: float = 2.0
DEFAULT_REQUEST_TIMEOUT: int = 60
PROXY_ENV_KEYS: tuple[str, ...] = ("PROXY", "PROXY_URL")


def _env_proxy_url() -> str | None:
    for key in PROXY_ENV_KEYS:
        raw = os.getenv(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            return s
    return None


def _env_chat_id() -> int | str | None:
    raw = os.getenv(DEFAULT_CHAT_ID_ENV)
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return s


class TelegramService:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[int | str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        proxy_url: Optional[str] = None,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        env_token = os.getenv(DEFAULT_BOT_TOKEN_ENV)
        env_cid = _env_chat_id()
        env_proxy = _env_proxy_url()
        self.bot_token: str = bot_token or env_token or ""
        self.chat_id: int | str | None = chat_id if chat_id is not None else env_cid
        self.max_retries: int = max_retries if max_retries > 0 else DEFAULT_MAX_RETRIES
        self.proxy_url: str | None = proxy_url if proxy_url is not None else env_proxy
        self.request_timeout: int = int(request_timeout) if int(request_timeout) > 0 else DEFAULT_REQUEST_TIMEOUT
        self._session: Optional[AiohttpSession] = None

        if not self.bot_token:
            raise RuntimeError(
                f"TelegramService: missing bot token. Set env {DEFAULT_BOT_TOKEN_ENV} or pass bot_token."
            )
        if self.chat_id in (None, ""):
            raise RuntimeError(
                f"TelegramService: missing chat id. Set env {DEFAULT_CHAT_ID_ENV} or pass chat_id."
            )

        self._bot: Optional[Bot] = None
        logger.info(
            f"[TelegramService] initialized (chat_id={self.chat_id!r}, "
            f"max_retries={self.max_retries}, request_timeout={self.request_timeout}s)"
        )
        if self.proxy_url:
            # mask basic auth if present: http://user:pass@host:port -> http://***:***@host:port
            try:
                from urllib.parse import urlparse, urlunparse
                parsed = urlparse(self.proxy_url)
                if parsed.username or parsed.password:
                    masked = parsed._replace(netloc=f"{'***' if parsed.username else ''}:{'***' if parsed.password else ''}@{parsed.hostname}{(':'+str(parsed.port)) if parsed.port else ''}")
                    logger.info(f"[TelegramService] Proxy configured: {urlunparse(masked)}")
                else:
                    logger.info(f"[TelegramService] Proxy configured: {self.proxy_url}")
            except Exception:
                logger.info(f"[TelegramService] Proxy configured: {self.proxy_url[:60]}...")
        else:
            logger.info("[TelegramService] Running without proxy")

    async def start(self) -> None:
        if self._bot is not None:
            return

        timeout = ClientTimeout(total=float(self.request_timeout))
        if self.proxy_url:
            self._session = AiohttpSession(
                proxy=self.proxy_url,
                timeout=timeout,
            )
            logger.info(
                f"[TelegramService] starting Bot via proxy (timeout={self.request_timeout}s)..."
            )
            self._bot = Bot(
                token=self.bot_token,
                session=self._session,
                default=DefaultBotProperties(parse_mode=None, protect_content=None),
            )
        else:
            self._session = AiohttpSession(timeout=timeout)
            logger.info(
                f"[TelegramService] starting Bot DIRECT (no proxy, timeout={self.request_timeout}s)..."
            )
            self._bot = Bot(
                token=self.bot_token,
                session=self._session,
                default=DefaultBotProperties(parse_mode=None, protect_content=None),
            )
        logger.info("[TelegramService] aiogram Bot started")

    async def stop(self) -> None:
        if self._bot is None and self._session is None:
            return
        session_to_close = self._session
        try:
            if self._bot is not None:
                try:
                    await self._bot.session.close()
                except Exception as e:
                    logger.debug(f"[TelegramService] bot.session.close ignored: {e}")
        finally:
            self._bot = None
            if session_to_close is not None:
                try:
                    await session_to_close.close()
                except Exception as e:
                    logger.debug(f"[TelegramService] AiohttpSession.close ignored: {e}")
            self._session = None
            logger.info("[TelegramService] aiogram Bot stopped")

    async def __aenter__(self) -> "TelegramService":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

    async def upload_photo(self, image_bytes: bytes | io.BytesIO, caption: str = "") -> str:
        if self._bot is None:
            await self.start()
        assert self._bot is not None

        if isinstance(image_bytes, io.BytesIO):
            raw_bytes = image_bytes.getvalue()
        else:
            raw_bytes = bytes(image_bytes)

        if not raw_bytes:
            raise ValueError("upload_photo received empty bytes")

        input_file = BufferedInputFile(file=raw_bytes, filename="photo.jpg")

        safe_caption = caption or ""
        if len(safe_caption) > 1024:
            safe_caption = safe_caption[: 1024 - 3] + "..."

        last_error: Optional[BaseException] = None
        attempt: int = 0
        via_proxy = bool(self.proxy_url)
        while attempt < self.max_retries:
            attempt += 1
            try:
                msg: Message = await self._bot.send_photo(
                    chat_id=self.chat_id,
                    photo=input_file,
                    caption=safe_caption or None,
                    disable_notification=True,
                )
                if not msg.photo:
                    raise RuntimeError("send_photo succeeded but msg.photo is empty")
                best = msg.photo[-1]
                file_id = str(best.file_id)
                logger.info(
                    f"[TelegramService] photo uploaded OK "
                    f"({len(raw_bytes)} bytes, cap={len(safe_caption)} chars, file_id[:24]={file_id[:24]!r}...)"
                )
                del raw_bytes
                del input_file
                gc.collect()
                return file_id
            except TelegramRetryAfter as e:
                wait_for = float(getattr(e, "retry_after", 10) or 10)
                sleep_s = wait_for + 1.0
                logger.warning(
                    f"[TelegramService] retry_after={wait_for}s requested by TG (attempt {attempt}/{self.max_retries}). Sleep {sleep_s:.1f}s ..."
                )
                await asyncio.sleep(sleep_s)
                last_error = e
                continue
            except (TelegramNetworkError, TelegramServerError) as e:
                backoff = DEFAULT_RETRY_BACKOFF_BASE ** (attempt - 1)
                proxy_hint = " (PROXY used — check proxy reachability/auth)" if via_proxy else " (no proxy — check internet / TG block)"
                logger.warning(
                    f"[TelegramService] {type(e).__name__} (attempt {attempt}/{self.max_retries}): {e}{proxy_hint}. Sleep {backoff:.1f}s ..."
                )
                await asyncio.sleep(backoff)
                last_error = e
                continue
            except ClientError as e:
                backoff = DEFAULT_RETRY_BACKOFF_BASE ** (attempt - 1)
                proxy_hint = " PROXY connection dropped — check proxy URL, port and credentials." if via_proxy else " Direct connection dropped — check internet / TG availability."
                logger.warning(
                    f"[TelegramService] aiohttp ClientError {type(e).__name__} (attempt {attempt}/{self.max_retries}): {e}.{proxy_hint}. Sleep {backoff:.1f}s ..."
                )
                await asyncio.sleep(backoff)
                last_error = e
                continue
            except TimeoutError as e:
                backoff = DEFAULT_RETRY_BACKOFF_BASE ** (attempt - 1)
                proxy_hint = " (PROXY timeout — proxy slow/unreachable)" if via_proxy else " (no proxy — timeout to TG)"
                logger.warning(
                    f"[TelegramService] TimeoutError (attempt {attempt}/{self.max_retries}): request > {self.request_timeout}s{proxy_hint}. Sleep {backoff:.1f}s ..."
                )
                await asyncio.sleep(backoff)
                last_error = e
                continue
            except Exception as e:
                last_error = e
                proxy_hint = " (PROXY in use — see exception chain for proxy errors)" if via_proxy else ""
                logger.exception(
                    f"[TelegramService] unexpected {type(e).__name__} on send_photo (attempt {attempt}/{self.max_retries}){proxy_hint}"
                )
                raise

        logger.error(
            f"[TelegramService] upload_photo failed AFTER ALL {self.max_retries} attempts. "
            f"Last error: {type(last_error).__name__}: {last_error}. "
            f"Proxy={'configured' if via_proxy else 'OFF'} timeout={self.request_timeout}s"
        )
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"upload_photo failed after {self.max_retries} attempts")

    async def download_file(self, tg_file_id: str, *, request_timeout: Optional[int] = None) -> bytes:
        if self._bot is None:
            await self.start()
        assert self._bot is not None

        if not tg_file_id:
            raise ValueError("download_file received empty tg_file_id")

        timeout = int(request_timeout) if request_timeout else self.request_timeout
        last_error: Optional[BaseException] = None
        attempt: int = 0
        via_proxy = bool(self.proxy_url)

        while attempt < self.max_retries:
            attempt += 1
            try:
                tg_file = await self._bot.get_file(file_id=tg_file_id, request_timeout=timeout)
                if tg_file is None or not getattr(tg_file, "file_id", None):
                    raise RuntimeError(f"get_file returned empty result for file_id={tg_file_id!r}")
                buf = io.BytesIO()
                downloaded = await self._bot.download(
                    file=tg_file,
                    destination=buf,
                    timeout=timeout,
                )
                raw_bytes = buf.getvalue()
                if not raw_bytes:
                    raise RuntimeError(f"download returned 0 bytes for file_id={tg_file_id!r}")
                logger.info(
                    f"[TelegramService] download_file OK "
                    f"file_id={tg_file_id[:20]}... -> bytes={len(raw_bytes)} (attempt {attempt}/{self.max_retries})"
                )
                del buf
                gc.collect()
                return raw_bytes
            except TelegramRetryAfter as e:
                wait_for = float(getattr(e, "retry_after", 10) or 10)
                sleep_s = wait_for + 1.0
                logger.warning(
                    f"[TelegramService] download retry_after={wait_for}s requested by TG "
                    f"(attempt {attempt}/{self.max_retries}). Sleep {sleep_s:.1f}s ..."
                )
                await asyncio.sleep(sleep_s)
                last_error = e
                continue
            except (TelegramNetworkError, TelegramServerError) as e:
                backoff = DEFAULT_RETRY_BACKOFF_BASE ** (attempt - 1)
                proxy_hint = " (PROXY used — check proxy reachability/auth)" if via_proxy else " (no proxy — check internet / TG block)"
                logger.warning(
                    f"[TelegramService] download {type(e).__name__} (attempt {attempt}/{self.max_retries}): {e}{proxy_hint}. Sleep {backoff:.1f}s ..."
                )
                await asyncio.sleep(backoff)
                last_error = e
                continue
            except ClientError as e:
                backoff = DEFAULT_RETRY_BACKOFF_BASE ** (attempt - 1)
                proxy_hint = " PROXY connection dropped — check proxy URL, port and credentials." if via_proxy else " Direct connection dropped — check internet / TG availability."
                logger.warning(
                    f"[TelegramService] download aiohttp ClientError {type(e).__name__} (attempt {attempt}/{self.max_retries}): {e}.{proxy_hint}. Sleep {backoff:.1f}s ..."
                )
                await asyncio.sleep(backoff)
                last_error = e
                continue
            except TimeoutError as e:
                backoff = DEFAULT_RETRY_BACKOFF_BASE ** (attempt - 1)
                proxy_hint = " (PROXY timeout — proxy slow/unreachable)" if via_proxy else " (no proxy — timeout to TG)"
                logger.warning(
                    f"[TelegramService] download TimeoutError (attempt {attempt}/{self.max_retries}): request > {timeout}s{proxy_hint}. Sleep {backoff:.1f}s ..."
                )
                await asyncio.sleep(backoff)
                last_error = e
                continue
            except Exception as e:
                last_error = e
                proxy_hint = " (PROXY in use — see exception chain for proxy errors)" if via_proxy else ""
                logger.exception(
                    f"[TelegramService] unexpected {type(e).__name__} on download_file (attempt {attempt}/{self.max_retries}){proxy_hint}"
                )
                raise

        logger.error(
            f"[TelegramService] download_file failed AFTER ALL {self.max_retries} attempts. "
            f"Last error: {type(last_error).__name__}: {last_error}. "
            f"Proxy={'configured' if via_proxy else 'OFF'} timeout={timeout}s"
        )
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"download_file failed after {self.max_retries} attempts")
