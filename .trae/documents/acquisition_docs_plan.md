# Acquisition & CDN Docs Implementation Plan (Layer 01)

## Repository Research — уже выполнено (P1 complete). Точные сигнатуры, CLI-флаги, SQL-конструкции извлечены из реального кода:

### Точные данные из кодовой базы (verified Grep + Read):
1. **CLI Справочник (argparse)**:
   - `scripts/run_discovery.py` — **БЕЗ аргументов** (нет argparse в коде, просто async main).
   - `scripts/run_crawler.py` → **`--limit-categories` (int, default=None)**, **`--page-size-hint` (int, default=120)**.
   - `scripts/run_worker.py` → **`--limit` (int, None)**, **`--interval` (float, default=2.5)**, **`--headless` (action=store_true default=True)**, **`--headed` (dest=headless, store_false, видимый браузер)**.
   - `scripts/fix_broken_titles.py` → **`--limit` (int default=None)** (L256).
   - `scripts/fix_cover.py` — **БЕЗ CLI argparse** (batch_size=200 захардкожен в L40).
2. **SKIP LOCKED SQL**: src/modules/worker/album_worker.py L91-L117 → CTE candidate `select...Album.status='pending'...limit 1.with_for_update(skip_locked=True)`, затем UPDATE returning Album.id → status='processing', updated_at=now().
3. **PlaywrightService сигнатуры**:
   - `__init__(self, proxy_url: Optional[str] = None, user_agent: str = DEFAULT_USER_AGENT, referer: str = DEFAULT_YUPOO_REFERER, navigation_timeout_ms: int = 60_000, request_timeout_ms: int = 45_000, headless: bool = True)`
   - Константы: DEFAULT_NAVIGATION_TIMEOUT_MS=60_000, DEFAULT_REQUEST_TIMEOUT_MS=45_000, DEFAULT_JITTER_MIN=1.0, MAX=3.0, user_agent=Chrome/126.0.0.0 Win10, DEFAULT_YUPOO_REFERER="https://3125tiger.x.yupoo.com/".
   - Методы: `async start()`, `async stop()`, `async get_page_content(url:str) -> str`, `async get_image_bytes(url:str, referer: Optional[str]=None) -> bytes`, plus async context manager.
4. **TelegramService сигнатуры**:
   - `__init__(self, bot_token: Optional[str]=None, chat_id: Optional[int | str]=None, max_retries: int=3, proxy_url: Optional[str]=None, request_timeout: int=60)`
   - Env vars: TG_TOKEN, TG_CHAT_ID, PROXY/PROXY_URL (L35).
   - Методы: `is_running()->bool`, `async start()`, `async stop()`, `async upload_photo(image_bytes: bytes | io.BytesIO, caption: str="") -> str (file_id)`, `async download_file(tg_file_id:str, *, request_timeout:Optional[int]=None) -> bytes`.
   - Обработка TelegramRetryAfter: L233-L240 wait_for + 1.0 sec safety margin.
5. **security.py**:
   - `def clean_album_title(title: str, category_name: Optional[str]=None, album_id: Optional[int]=None) -> str` L206, uses 8 regex families (PRICE 8, SIZE 2, URL 4, TECH 9, CHINESE, HYPHEN variants, ARTIFACT PROTECT). Fallback chain: digits+brand → brand+#id → digits → sanitized orig → brand → fallback orig.
   - `def sanitize_category_brand(category_name: Optional[str]) -> str` L135: strips parentheses, keeps A-Za-z0-9 &'-. — removes everything else, multispace collapse.

## Scope / Files & Modules (что меняем)
- **[EDIT 1]** `docs/01-acquisition-and-cdn/explanation.md`: 4 секции CONCEPTUAL/DEEP TECH: (1.1 Yupoo 567 bypass + Playwright Stealth architecture), (1.2 Telegram as free CDN — io.BytesIO streaming, file_id permanent pointer economics vs S3), (1.3 Postgres SKIP LOCKED queue race condition-free architecture), (1.4 Idempotency & transaction handling — _find_existing_tg_file_id dedup, one commit per album L479 success, rollback on error L490-L492).
- **[EDIT 2]** `docs/01-acquisition-and-cdn/how-to.md`: 7 RECIPES exactly user-specified + READY commands from venv Scripts/python: Recipe 1 run_discovery (no args), 2 run_crawler --limit-categories N --page-size-hint 120 + CRAWL_KEYWORDS env, 3 run_worker --limit 10 --interval 2.5 --headed test, 4 docker-compose scale worker=N parallel, 5 SQL UPDATE reset processing→pending stuck tasks, 6 fix_cover.py python -m scripts.fix_cover, 7 fix_broken_titles --limit N.
- **[EDIT 3]** `docs/01-acquisition-and-cdn/reference.md`: STRICT STRUCTURED REFERENCE: 3.1 CLI Scripts TABLES per script with flag/type/default/help columns, 3.2 security.py: clean_album_title signature + regex list table, sanitize_category_brand signature, 3.3 PlaywrightService class TABLE __init__ params + methods TABLE + constants TABLE, 3.4 TelegramService TABLE __init__ params, methods upload_photo/download_file return types, env vars TABLE, TelegramRetryAfter algo pseudo-code.

## Dependency-ordered Implementation Steps
1. **Edit Step 1 explanation.md**: replace skeleton H1 + 1 paragraph user-specified skeleton with full 4-section doc. No other edits.
2. **Edit Step 2 how-to.md**: replace skeleton with 7 recipes bash code blocks, .env CRAWL_KEYWORDS section, DBeaver verification SQL snippet.
3. **Edit Step 3 reference.md**: replace skeleton with 4 TABLE sections (CLI, security.py, PlaywrightService, TelegramService) ALL sourced verbatim from research above (NO fabricated numbers/flags).
4. **Post validation P7**: run Grep on all 3 docs — 0 fabricated flag names (--something-not-in-research), verify that for every --flag, the exact default value matches argparse defaults (120 page-size-hint, interval 2.5 etc). Verify regex names in reference clean_album_title match security.py L8-L81 family names.

## Dependencies & Considerations
- **Python interpreter path**: В рецептах how-to.md всегда использовать абсолютный путь venv `.\\.venv\\Scripts\\python.exe scripts\\run_discovery.py` а не `python ...` потому что системный интерпретатор не имеет dotenv и выкидывал ModuleNotFound earlier (из Phase3 bug).
- **ВАЖНО: НИКАКОЙ выдуманной контент — 100% факты из кода.** Нельзя придумывать несуществующие скрипты, несуществующие env vars, несуществующие методы. Everything must trace to real code files.
- Bash code blocks: ` ```bash ` для команд Windows (PowerShell — пути c backslash).
- SQL code blocks: ` ```sql ` для reset pending рецепта 5 и проверки в DBeaver рецепта 2.
- Python/signature tables: 4 columns = Name, Type, Default, Description (для классов/методов: Signature, Params, Return, Raises).
- Sourcing photos: если doc ссылается на функцию/метод/флаг, указываем файл источник в виде "Реализация: [album_worker.py L90-L117](file:///c:/Users/...)" чтобы пользователь мог кликнуть и проверить.

## Validation (mandatory before user confirmation)
1. **Flag-name check**: for every CLI flag name used in how-to.md + reference, grep it from original script argparse definition — MUST match exactly (e.g. no --limit-albums if argparse says --limit-categories).
2. **Default value check**: every flag's default number (page-size-hint=120, interval=2.5, max_retries=3, request_timeout=60) must match research.
3. **Content-length sanity**: Explanation ~1500-2500 words, How-to ~1000-2000, Reference ~6 tables. No novelization; no fabricated story-telling content beyond research.
4. **Russian professional technical language**: No english terms where Russian exists, but keep standard tech terms (Playwright, SKIP LOCKED, Referer header, file_id, BytesIO, aiogram) as is (standard usage in RU dev community).

## Risks
1. **Risk: Fabricated CLI/env values leak (user explicit prohibition)**. Mitigation: after write, grep every flag/env from doc into argparse+dotenv source files; if any has 0 matches — rewrite immediately.
2. **Risk: Explanation too high-level (no code specifics)**. Mitigation: every 3rd paragraph of Explanation cites the actual file lines/real function names (e.g. "функция `_find_existing_tg_file_id` в [album_worker.py#L182-L195] проверяет существование перед send_photo").
3. **Risk: How-to commands fail due to wrong cwd/interpreter**. Mitigation: every command prefixed with `cd c:\\Users\\Void\\Desktop\\yupoo-parser` ; uses `.\\.venv\\Scripts\\python.exe` explicitly (see Phase3 resolved bug ModuleNotFound).
