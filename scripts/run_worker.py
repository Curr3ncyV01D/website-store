from __future__ import annotations

import argparse
import asyncio
import gc
import os
import random
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from loguru import logger

from src.db.session import dispose_engine, get_session_factory
from src.modules.worker.album_worker import AlbumWorker
from src.services.playwright_service import PlaywrightService
from src.services.telegram_service import TelegramService


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Yupoo -> Telegram CDN worker (memory-only, no disk)")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only first N pending albums attempts (success OR error both count against limit, for MVP tests 5-10)",
    )
    p.add_argument(
        "--interval",
        type=float,
        default=2.5,
        help="Pause in seconds between albums attempt loops (default 2.5; suggest 2-5)",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run Playwright in headless mode (default True)",
    )
    p.add_argument(
        "--headed",
        dest="headless",
        action="store_false",
        help="Run Playwright with visible browser",
    )
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    logger.info(
        f"=== run_worker.py START (limit={args.limit}, interval={args.interval}s, headless={args.headless}) ==="
    )

    session_factory = get_session_factory()
    attempts_total_local: int = 0

    try:
        async with TelegramService() as tg:
            async with PlaywrightService(headless=args.headless) as browser:
                worker = AlbumWorker(
                    session_factory=session_factory,
                    browser=browser,
                    tg=tg,
                )
                while True:
                    if args.limit is not None and attempts_total_local >= args.limit:
                        logger.info(
                            f"run_worker.py: hit --limit {args.limit} ({attempts_total_local} album attempts), stop loop."
                        )
                        break

                    try:
                        album = await worker.get_next_pending_album()
                    except Exception as e:
                        logger.exception(
                            f"run_worker.py: get_next_pending_album DB operation failed: {type(e).__name__}. Sleep 5s and retry (NOT counted against --limit)."
                        )
                        await asyncio.sleep(5.0)
                        continue

                    if album is None:
                        logger.success(
                            f"run_worker.py: DB has NO pending albums left. "
                            f"Attempts so far: {attempts_total_local}. Worker exiting cleanly."
                        )
                        break

                    album_id = album.id
                    try:
                        await worker.process_one_album(album)
                    except Exception as e:
                        logger.exception(
                            f"run_worker.py: Uncaught outer exception during album id={album_id}: {type(e).__name__} — counted as attempt against --limit"
                        )
                    finally:
                        attempts_total_local += 1
                        s = worker.stats
                        logger.debug(
                            f"run_worker.py: after album id={album_id} => attempts_local={attempts_total_local} "
                            f"stats[attempts={s.attempts}, success={s.success_albums}, errors={s.error_albums}, "
                            f"new_tg={s.new_tg_images}, reused_existing={s.skipped_existing_images}, broken={s.skipped_broken_images}]"
                        )
                        try:
                            del album
                        except Exception:
                            pass
                        gc.collect()
                        if args.limit is None or attempts_total_local < args.limit:
                            pause = random.uniform(
                                max(0.0, args.interval * 0.6), args.interval * 1.4
                            )
                            logger.info(
                                f"run_worker.py: sleep {pause:.2f}s between albums ..."
                            )
                            await asyncio.sleep(pause)

                s = worker.stats
                logger.success(
                    "=== run_worker.py FINAL STATS ===========================================\n"
                    f"  attempts (local --limit counter) : {attempts_total_local}\n"
                    f"  worker.stats.attempts             : {s.attempts}\n"
                    f"  success_albums -> status completed: {s.success_albums}\n"
                    f"  error_albums   -> status error    : {s.error_albums}\n"
                    f"  new_tg_images  (fresh uploads)    : {s.new_tg_images}\n"
                    f"  skipped_existing_images (idempotent reuse): {s.skipped_existing_images}\n"
                    f"  skipped_broken_images (tiny/404)  : {s.skipped_broken_images}\n"
                    "========================================================================"
                )
    finally:
        try:
            await dispose_engine()
        except Exception as e:
            logger.debug(f"run_worker.py dispose_engine ignored: {e}")

    logger.success(
        f"=== run_worker.py finished (total_local_attempts={attempts_total_local}) ==="
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
