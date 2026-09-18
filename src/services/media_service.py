from __future__ import annotations

import os
import sys
import zlib
import struct
from pathlib import Path as StdLibPath
from typing import Optional, Any, TYPE_CHECKING

import aiofiles
from fastapi.responses import FileResponse, Response
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if TYPE_CHECKING:
    from src.db.models import Image


DEFAULT_CACHE_CONTROL: str = "public, max-age=86400"
DEFAULT_PLACEHOLDER_CACHE_CONTROL: str = "public, max-age=3600"
DEFAULT_FAVICON_CACHE_CONTROL: str = "public, max-age=7200"

FAVICON_SVG_FALLBACK_TEMPLATE: str = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
    '<rect width="64" height="64" rx="12" fill="#09090b"/>'
    '<text x="50%" y="54%" text-anchor="middle" dominant-baseline="middle" '
    'font-family="Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif" '
    'font-weight="800" font-size="28" fill="{text_fill}">{text}</text>'
    '</svg>'
)


class MediaService:
    """
    Сервисный слой для работы с медиа (изображения альбомов, favicon, плейсхолдеры).

    Ответственность:
      - Управление директориями кэша и статики (ensure_dirs)
      - Fallback-плейсхолдеры (PNG 1x1 при отсутствии реального файла)
      - Favicon (файл → SVG-заглушка без 404)
      - Изображения альбома: cache hit → DB lookup → TelegramService.download_file → cache write → response

    Разделение Concerns: логика media / image эндпоинтов вынесена из web.router (thin controller).
    """

    def __init__(
        self,
        project_root: str | os.PathLike[str] = PROJECT_ROOT,
        *,
        placeholder_filename: str = "no-image.png",
        favicon_filename: str = "favicon.ico",
        favicon_svg_text: str = "M",
        favicon_svg_text_fill: str = "#ffffff",
        cache_control_image: str = DEFAULT_CACHE_CONTROL,
        cache_control_placeholder: str = DEFAULT_PLACEHOLDER_CACHE_CONTROL,
        cache_control_favicon: str = DEFAULT_FAVICON_CACHE_CONTROL,
    ) -> None:
        self.project_root_path: StdLibPath = StdLibPath(os.fspath(project_root)).resolve()
        self.static_images_dir: StdLibPath = self.project_root_path / "static" / "images"
        self.media_cache_dir: StdLibPath = self.project_root_path / "data" / "media_cache"
        self.templates_dir: StdLibPath = self.project_root_path / "templates"
        self.placeholder_filename: str = placeholder_filename
        self.placeholder_path: StdLibPath = self.static_images_dir / placeholder_filename
        self.favicon_filename: str = favicon_filename
        self.favicon_path: StdLibPath = self.static_images_dir / favicon_filename
        self.favicon_svg_fallback: str = FAVICON_SVG_FALLBACK_TEMPLATE.format(
            text_fill=favicon_svg_text_fill, text=favicon_svg_text
        )
        self.cache_control_image: str = cache_control_image
        self.cache_control_placeholder: str = cache_control_placeholder
        self.cache_control_favicon: str = cache_control_favicon

    # ------------------------------------------------------------------
    # Lifecycle / directory helpers
    # ------------------------------------------------------------------
    def ensure_dirs(self) -> None:
        for d in (self.static_images_dir, self.media_cache_dir, self.templates_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"[media_service] couldn't ensure dir {d}: {e}")

    @staticmethod
    def build_minimal_placeholder_png_bytes() -> bytes:
        """Pure function — возвращает 1x1 серый PNG-плейсхолдер (без зависимостей)."""

        def _chunk(tag: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + tag
                + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            )

        width, height = 1, 1
        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        raw = b"\x00\xaa\xaa\xaa"
        idat = zlib.compress(raw, 9)
        return sig + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")

    async def ensure_placeholder_exists(self) -> None:
        self.ensure_dirs()
        if self.placeholder_path.exists() and self.placeholder_path.stat().st_size > 10:
            return
        try:
            data = self.build_minimal_placeholder_png_bytes()
            async with aiofiles.open(self.placeholder_path, "wb") as f:
                await f.write(data)
            logger.info(
                f"[media_service] wrote placeholder PNG to {self.placeholder_path} ({len(data)} bytes)"
            )
        except Exception as e:
            logger.exception(
                f"[media_service] FAILED to write placeholder {self.placeholder_path}: {e}"
            )

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    def cache_path_for(self, image_id: int) -> StdLibPath:
        return self.media_cache_dir / f"{int(image_id)}.jpg"

    # ------------------------------------------------------------------
    # Response builders
    # ------------------------------------------------------------------
    def placeholder_response(self, *, error_message: Optional[str] = None) -> Response:
        if self.placeholder_path.exists():
            resp = FileResponse(
                path=str(self.placeholder_path),
                media_type="image/png",
            )
            resp.headers["Content-Disposition"] = "inline"
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["Cache-Control"] = self.cache_control_placeholder
            if error_message:
                resp.headers["X-Placeholder-Reason"] = str(error_message)[:200]
            return resp
        data = self.build_minimal_placeholder_png_bytes()
        resp = Response(content=data, media_type="image/png")
        resp.headers["Content-Disposition"] = "inline"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = self.cache_control_placeholder
        if error_message:
            resp.headers["X-Placeholder-Reason"] = str(error_message)[:200]
        return resp

    def favicon_response(self) -> Response:
        try:
            if (
                self.favicon_path.exists()
                and self.favicon_path.is_file()
                and self.favicon_path.stat().st_size > 0
            ):
                resp = FileResponse(
                    path=str(self.favicon_path),
                    media_type="image/x-icon",
                    filename=self.favicon_filename,
                )
                resp.headers["Cache-Control"] = self.cache_control_favicon
                return resp
        except Exception as e:
            logger.debug(
                f"[media_service] favicon file open fail -> SVG fallback: {type(e).__name__}"
            )
        fallback_bytes = self.favicon_svg_fallback.encode("utf-8")
        resp = Response(content=fallback_bytes, media_type="image/svg+xml")
        resp.headers["Cache-Control"] = self.cache_control_favicon
        return resp

    # ------------------------------------------------------------------
    # Main flow: /media/image/{id}
    # ------------------------------------------------------------------
    def _fetch_tg_service(self, app_state: Any) -> Optional[Any]:
        """Извлечь TelegramService singleton из app.state или request.app.state."""
        tg = getattr(app_state, "tg_service", None)
        if tg is None:
            state = getattr(app_state, "state", None)
            if state is not None:
                tg = getattr(state, "tg_service", None)
        return tg

    async def serve_image(
        self,
        image_id: int,
        session: AsyncSession,
        tg_service: Any,
    ) -> Response:
        """
        Полный цикл получения изображения:
        1. CACHE HIT — возвращаем сразу из FS
        2. DB lookup — получить Image.tg_file_id по images.id
        3. TelegramService.download_file(tg_file_id) — получить байты
        4. async write cache (aiofiles) в media_cache
        5. FileResponse или in-memory Response
        В любом падении кейсе → placeholder_response.
        """
        real_image_id = int(image_id)
        cache_path: StdLibPath = self.cache_path_for(real_image_id)

        # 1) Fast path — cache hit
        if cache_path.exists():
            size = cache_path.stat().st_size
            if size > 0:
                logger.debug(
                    f"[media_service] /image/{real_image_id}: CACHE HIT from {cache_path.name} ({size} bytes)"
                )
                resp = FileResponse(path=cache_path, media_type="image/jpeg")
                resp.headers["Content-Disposition"] = "inline"
                resp.headers["X-Content-Type-Options"] = "nosniff"
                resp.headers["Cache-Control"] = self.cache_control_image
                resp.headers["X-Cache"] = "HIT"
                return resp
            try:
                cache_path.unlink(missing_ok=True)
            except Exception:
                pass

        # 2) DB lookup for Image.tg_file_id
        img: Optional["Image"] = None
        try:
            from src.db.models import Image as _Image

            q = await session.execute(
                select(_Image).where(_Image.id == real_image_id).limit(1)
            )
            img = q.scalar_one_or_none()
        except Exception as e:
            logger.exception(
                f"[media_service] /image/{real_image_id}: DB select Image failed -> placeholder"
            )
            return self.placeholder_response(error_message=f"db_select_error: {type(e).__name__}")

        if img is None:
            logger.warning(
                f"[media_service] /image/{real_image_id}: NOT FOUND in DB images.id -> placeholder"
            )
            return self.placeholder_response(error_message="image_id_not_found")

        tg_file_id = img.tg_file_id
        if not tg_file_id:
            logger.warning(
                f"[media_service] /image/{real_image_id}: empty tg_file_id in DB (row exists but not uploaded yet) -> placeholder"
            )
            return self.placeholder_response(error_message="empty_tg_file_id")

        if tg_service is None:
            logger.error(
                f"[media_service] /image/{real_image_id}: TelegramService singleton MISSING "
                f"(lifespan failed or TG_TOKEN/TG_CHAT_ID wrong? check startup logs) -> placeholder"
            )
            return self.placeholder_response(error_message="tg_service_missing")

        # 3) Download from Telegram
        try:
            raw_bytes: bytes = await tg_service.download_file(str(tg_file_id))
        except Exception as e:
            logger.exception(
                f"[media_service] /image/{real_image_id}: TelegramService download_file failed -> placeholder"
            )
            return self.placeholder_response(
                error_message=f"tg_download_error: {type(e).__name__}: {str(e)[:120]}"
            )

        if not raw_bytes:
            logger.error(
                f"[media_service] /image/{real_image_id}: Telegram returned 0 bytes -> placeholder"
            )
            return self.placeholder_response(error_message="tg_empty_bytes")

        # 4) async write cache
        try:
            async with aiofiles.open(cache_path, "wb") as f:
                await f.write(raw_bytes)
            logger.info(
                f"[media_service] /image/{real_image_id}: CACHE STORED -> {cache_path.name} ({len(raw_bytes)} bytes)"
            )
        except Exception as e:
            logger.warning(
                f"[media_service] /image/{real_image_id}: failed to write cache file {cache_path}: {e} — serving bytes from memory"
            )

        # 5) Response
        resp: Response
        if cache_path.exists() and cache_path.stat().st_size > 0:
            resp = FileResponse(path=cache_path, media_type="image/jpeg")
        else:
            resp = Response(content=raw_bytes, media_type="image/jpeg")
        resp.headers["Content-Disposition"] = "inline"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Cache-Control"] = self.cache_control_image
        resp.headers["X-Cache"] = "MISS (from TG this time)"
        return resp


_default_service: Optional[MediaService] = None


def get_default_media_service() -> MediaService:
    """Синглтон — один инстанс MediaService на весь процесс uvicorn."""
    global _default_service
    if _default_service is None:
        _default_service = MediaService()
    return _default_service


__all__ = [
    "DEFAULT_CACHE_CONTROL",
    "DEFAULT_PLACEHOLDER_CACHE_CONTROL",
    "DEFAULT_FAVICON_CACHE_CONTROL",
    "MediaService",
    "get_default_media_service",
]
