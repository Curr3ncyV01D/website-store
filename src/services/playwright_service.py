from __future__ import annotations

import asyncio
import random
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Optional, Type

import os
from dotenv import load_dotenv
from loguru import logger

try:
    import pkg_resources  # noqa: F401
except ModuleNotFoundError:
    import sys as _sys
    import importlib.resources as _ilr
    import types as _types

    class _PkgResourcesShim:
        @staticmethod
        def resource_string(package_or_requirement: str, resource_name: str) -> bytes:
            package = package_or_requirement
            parts = resource_name.lstrip("/").split("/")
            subpath = "/".join(parts[:-1]) if len(parts) > 1 else ""
            fname = parts[-1]
            traversable = _ilr.files(package)
            if subpath:
                traversable = traversable.joinpath(subpath)
            return (traversable / fname).read_bytes()

        @staticmethod
        def resource_filename(package_or_requirement: str, resource_name: str) -> str:
            return _ilr.as_file(
                _ilr.files(package_or_requirement).joinpath(resource_name.lstrip("/"))
            ).__enter__()

    _shim_mod = _types.ModuleType("pkg_resources")
    _shim_mod.resource_string = _PkgResourcesShim.resource_string
    _shim_mod.resource_filename = _PkgResourcesShim.resource_filename
    _sys.modules["pkg_resources"] = _shim_mod
    logger.debug("Injected pkg_resources shim via importlib.resources")

from playwright.async_api import (
    APIResponse,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from playwright_stealth import stealth_async

load_dotenv()

DEFAULT_YUPOO_REFERER: str = "https://3125tiger.x.yupoo.com/"
DEFAULT_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
DEFAULT_NAVIGATION_TIMEOUT_MS: int = 60_000
DEFAULT_REQUEST_TIMEOUT_MS: int = 45_000
DEFAULT_JITTER_MIN: float = 1.0
DEFAULT_JITTER_MAX: float = 3.0


def _jitter(min_s: float = DEFAULT_JITTER_MIN, max_s: float = DEFAULT_JITTER_MAX) -> float:
    return random.uniform(min_s, max_s)


class PlaywrightService(AbstractAsyncContextManager["PlaywrightService"]):
    def __init__(
        self,
        proxy_url: Optional[str] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        referer: str = DEFAULT_YUPOO_REFERER,
        navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
        request_timeout_ms: int = DEFAULT_REQUEST_TIMEOUT_MS,
        headless: bool = True,
    ) -> None:
        env_proxy = os.getenv("PROXY_URL")
        self.proxy_url: Optional[str] = proxy_url if proxy_url is not None else env_proxy
        self.user_agent: str = user_agent
        self.referer: str = referer
        self.navigation_timeout_ms: int = navigation_timeout_ms
        self.request_timeout_ms: int = request_timeout_ms
        self.headless: bool = headless

        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        logger.info(
            f"PlaywrightService initialized: "
            f"proxy={'ON' if self.proxy_url else 'OFF'}, "
            f"headless={self.headless}, "
            f"referer={self.referer}"
        )

    async def start(self) -> None:
        if self._browser is not None:
            logger.debug("PlaywrightService already started, skipping")
            return

        logger.info("Starting PlaywrightService ...")
        self._pw = await async_playwright().start()

        launch_kwargs: dict = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
            ],
        }
        if self.proxy_url:
            launch_kwargs["proxy"] = {"server": self.proxy_url}
            logger.debug(f"Using proxy: {self.proxy_url[:16]}...")

        self._browser = await self._pw.chromium.launch(**launch_kwargs)
        logger.info(f"Browser launched (chromium)")

        context_kwargs: dict = {
            "user_agent": self.user_agent,
            "viewport": {"width": 1920, "height": 1080},
            "locale": "en-US",
            "timezone_id": "Asia/Shanghai",
            "extra_http_headers": {
                "Referer": self.referer,
            },
        }
        self._context = await self._browser.new_context(**context_kwargs)
        logger.info("BrowserContext created with Yupoo referer pre-injected")

        self._page = await self._context.new_page()
        self._page.set_default_navigation_timeout(self.navigation_timeout_ms)
        self._page.set_default_timeout(self.request_timeout_ms)

        await stealth_async(self._page)
        logger.info("Stealth patches applied via playwright_stealth")

        await self._page.goto(self.referer, wait_until="domcontentloaded")
        await asyncio.sleep(_jitter(0.5, 1.5))
        logger.info(f"Warmed up context on referer page: {self.referer}")

    async def _ensure_started(self) -> None:
        if self._page is None or self._context is None or self._browser is None:
            await self.start()

    async def get_page_content(self, url: str) -> str:
        await self._ensure_started()
        assert self._page is not None
        assert self._context is not None

        j = _jitter()
        logger.info(f"GET page: {url} (jitter {j:.2f}s)")
        await asyncio.sleep(j)

        try:
            await self._context.set_extra_http_headers({"Referer": self.referer})
            response = await self._page.goto(url, wait_until="domcontentloaded")

            status = response.status if response is not None else 0
            if status == 567:
                logger.warning(f"Got HTTP 567 for {url}; re-warming and retrying once ...")
                await asyncio.sleep(_jitter(2.0, 4.0))
                await self._page.goto(self.referer, wait_until="domcontentloaded")
                await asyncio.sleep(_jitter(1.0, 2.5))
                response = await self._page.goto(url, wait_until="domcontentloaded")
                status = response.status if response is not None else 0

            if status and not (200 <= status < 400):
                logger.error(f"Bad HTTP status {status} for {url}")
                raise RuntimeError(f"HTTP {status} for {url}")

            html = await self._page.content()
            logger.info(f"Page loaded OK: {url} (status={status}, bytes={len(html)})")
            return html

        except PlaywrightTimeoutError as e:
            logger.error(f"Timeout loading page {url}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Failed to load page {url}: {type(e).__name__}")
            raise

    async def get_image_bytes(self, url: str, referer: Optional[str] = None) -> bytes:
        await self._ensure_started()
        assert self._page is not None
        assert self._context is not None

        effective_referer = referer if referer is not None else self.referer
        j = _jitter()
        logger.info(f"GET image bytes: {url} (referer={effective_referer[:40]}, jitter {j:.2f}s)")
        await asyncio.sleep(j)

        headers = {
            "Referer": effective_referer,
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": self.user_agent,
        }

        try:
            api_request = self._context.request
            response: APIResponse = await api_request.get(
                url,
                headers=headers,
                timeout=self.request_timeout_ms,
            )
            if not response.ok:
                logger.error(f"Image request failed: HTTP {response.status} for {url}")
                raise RuntimeError(f"Image HTTP {response.status} for {url}")

            body: bytes = await response.body()
            logger.info(f"Image downloaded OK: {url} ({len(body)} bytes, status={response.status})")
            return body

        except PlaywrightTimeoutError as e:
            logger.error(f"Timeout downloading image {url}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Failed to download image {url}: {type(e).__name__}")
            raise

    async def stop(self) -> None:
        errors: list[str] = []
        if self._page is not None:
            try:
                await self._page.close()
            except Exception as e:
                errors.append(f"page.close: {e}")
            finally:
                self._page = None
        if self._context is not None:
            try:
                await self._context.close()
            except Exception as e:
                errors.append(f"context.close: {e}")
            finally:
                self._context = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception as e:
                errors.append(f"browser.close: {e}")
            finally:
                self._browser = None
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception as e:
                errors.append(f"pw.stop: {e}")
            finally:
                self._pw = None
        if errors:
            logger.warning(f"Ignored errors during PlaywrightService.stop: {errors}")
        else:
            logger.info("PlaywrightService stopped cleanly")

    async def __aenter__(self) -> "PlaywrightService":
        await self.start()
        return self

    async def __aexit__(
        self,
        __exc_type: Optional[Type[BaseException]],
        __exc: Optional[BaseException],
        __tb: Optional[TracebackType],
    ) -> None:
        await self.stop()
