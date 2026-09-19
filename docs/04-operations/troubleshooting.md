# База знаний: Troubleshooting известных ошибок и отказов

Аннотация: Копирайт-подобная база знаний по диагностике и устранению наиболее часто встречающихся неисправностей: NoneType AttributeError в пайплайне парсинга, Authentication failed PostgreSQL и докер-компоуз сети, CORS/MIME-type ошибки статики и модулей ESM браузера, а также скролл-баги мобильного iOS и overflow-hidden race-conditions. Каждая запись KB следует научному формату дебага: Симптом → 3 гипотезы по убыванию вероятности → Пошаговый фикс с ссылкой на код.

---

## Диаграмма триажа: Дерево решений диагностики system failure

```mermaid
flowchart TD
    START["User Report: Ничего не работает 🚨"] --> HOST{"Где запущен инстанс?<br>Docker compose production <br>OR Local Windows venv dev?"}
    HOST -->|Docker Compose| D1["❓ docker compose ps<br>3 сервиса Up healthy?"]
    HOST -->|Local Windows venv| W1["❓ uvicorn запущен?<br>Health http://localhost:8765/health"]
    D1 -->|"db unhealthy<br>(restarting 5s cycle)"| T1["📌 T1 Postgres Auth 28P01<br>password failed"]
    D1 -->|web unhealthy exit code 1| T4["📌 T4 Alembic DAG integrity<br>can't locate revision"]
    D1 -->|worker unhealthy exit code 429| T3["📌 T3 Telegram API 429<br>Flood Control Retry-After"]
    D1 -->|Все 3 Up healthy → user жалуется на blank-page/interactivity| T5["📌 T5 Frontend Production Bugs<br>(Alpine race / PS aspect)"]
    W1 -->|HTTP 500 / Connection refused| DBLOCAL["Postgres контейнер запущен?<br>docker compose -f ... up -d db"]
    DBLOCAL -->|OK but still 5xx| T2["📌 T2 Crawler NoneType<br>AttributeError Yupoo 567"]
    W1 -->|"200 OK, services.tg = false"| T6["📌 T6 Health /health tg_available=false<br>TG_TOKEN invalid or no proxy"]
    W1 -->|200 OK UI works but Search blank / PS 404 CORS| T5
```

---

## T1. Postgres `password authentication failed` (28P01) — Docker Compose port & credential mismatch

### Симптом
```
docker compose logs db --tail 30
yupoo_db  | 2026-09-19 12:00:00.000 UTC [28] FATAL:  password authentication failed for user "postgres"
yupoo_db  | 2026-09-19 12:00:00.000 UTC [28] DETAIL:  Role "postgres" does not exist. Connection matched pg_hba.conf line ...
docker compose ps: db = restarting (healthcheck pg_isready fails retries 10×5s = 50s then loop)
```

### 3 гипотезы по вероятности

#### H1 (HIGH ~80%): Confusion host port `5433` vs container internal port `5432` + stale volume old password
Пользователь пытается подключиться DBeaver/psql к **localhost:5432** снаружи хоста, но docker-compose.yml явно пробрасывает **`5433:5432`** [docker-compose.yml:L15](file:///C:/Users/Void/Desktop/yupoo-parser/docker-compose.yml#L15). Или Postgres `postgres_data` volume создавался один раз со старым `DB_PASSWORD=postgres` в .env.example — потом пользователь сменил .env → но volume данные УЖЕ инициализированы старым паролем (db init scripts запускаются ТОЛЬКО на ПУСТОМ volume).

#### H2 (MEDIUM ~15%): .env и compose env vars DB_USER/DB_NAME mismatch
`.env.example` L7 шаблон `DB_PASSWORD=CHANGE_ME_STRONG_PASSWORD` не заменён → web сервис использует `postgres` default пароль через config.py:L53 default, а volume БД инициализирован `CHANGE_ME_STRONG_PASSWORD`. Compose environment L10-13 `${DB_USER:-postgres}` — переменная из `.env` выше приоритета чем default.

#### H3 (LOW ~5%): Windows Docker Desktop WSL2 postgres_data volume permission issue / `shm_size=128mb` overflow
WSL2 VHDX исчерпан (df -h /var/lib/docker <10Gb) или `shm_size=128mb` [docker-compose.yml:L9](file:///C:/Users/Void/Desktop/yupoo-parser/docker-compose.yml#L9) — B-tree индексы pg_trgm overflow.

### Фикс по гипотезам
1. **H1 fix (~3 step):**
   - DBeaver/psql: **ВСЕГДА localhost PORT=5433** снаружи хоста. Внутри compose-сети (`web` ↔ `db`) всё ещё `DB_PORT=5432` (имя сервиса `db` как хост, см .env.example L3-L5). **HARD RULE: external admin = 5433, internal docker network service-to-service = 5432.** Cross-ref: [layer 02 how-to PostgreSQL client config](file:///C:/Users/Void/Desktop/yupoo-parser/docs/02-database-and-storage/how-to.md).
   - Stale password volume reset:
     ```powershell
     cd c:\Users\Void\Desktop\yupoo-parser
     docker compose down -v   # ВНИМАНИЕ: -v УДАЛЯЕТ postgres_data volume, теряете все БД данные (бэкап first)
     # затем правим .env DB_PASSWORD=новый_сильный_пароль ОДИН раз
     docker compose up -d db  # fresh init с новым паролем
     docker compose up -d web worker
     ```
2. **H2 fix:** Проверить .env password строка L7 `DB_PASSWORD=XXX` — убедиться нет лишних пробелов/кавычек. Config.py Pydantic `extra=ignore` config.py:L50, лишнее не вызывает ошибки, но убедиться 4 DB env vars match между .env и compose environment section.
3. **H3 fix:** `docker system prune -f` или расширить WSL2 .wslconfig memory=8GB swap=4GB. shm_size → поднять 256mb compose L9 если pg_trgm реиндекс OOM.

---

## T2. Crawler NoneType / AttributeError: `'NoneType' object has no attribute 'strip'` (Yupoo 567 Hotlink Protection)

### Симптом
```powershell
.\.venv\Scripts\python.exe scripts\run_crawler.py
  ... crawler.py L123 ...
AttributeError: 'NoneType' object has no attribute 'strip'
  title = extracted_title.strip()   # extracted_title = None!
# или
PlaywrightService L78 fetch: HTTP Status 567 Yupoo "Unauthorized direct link" (Yupoo specific anti-scrape protection)
```

### 3 гипотезы

#### H1 HIGH ~85%: НЕ прогрели Playwright session через discovery перед crawler (phase 01 lesson)
`run_discovery.py` делает warm-up: заходит на главную yupoo.com, кукисы + __cf_bm Cloudflare challenge + Referer chain установлены. Если пропустить discovery и сразу запустить crawler — получаем `567 Unauthorized`. Cross-ref: [layer 01 explanation §2.2 Yupoo 567 hotlink bypass warmup](file:///C:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/explanation.md).

#### H2 MEDIUM ~12%: Прокси не настроен, RU IP Yupoo direct block
Нет PROXY_URL в .env.example L18 uncomment. Yupoo банит RU ASN прямо на TCP-уровне (RST пакет до TLS handshake). `PROXY_URL=socks5://user:pass@...:1080` разлочивает. Cross-ref: [layer 01 how-to R1 proxy setup](file:///C:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/how-to.md).

#### H3 LOW ~3%: Playwright Chromium не установлен (--with-deps missing)
Windows venv локально не запускали `playwright install chromium --with-deps`. В Dockerfile это RUN шаг L14, но локальный Windows dev требует ручного install.

### Фикс
1. **H1 warm-up required (MANDATORY RUN ORDER):**
   ```powershell
   # STEP 1 FIRST — warm-up playwright session + build task queue
   .\.venv\Scripts\python.exe scripts\run_discovery.py --keywords "ADIDAS,NIKE,JORDAN"
   # STEP 2 ONLY AFTER discovery returns SUCCESS — run crawler
   .\.venv\Scripts\python.exe scripts\run_crawler.py --max 10
   ```
   Run discovery first каждый день перед crawler, иначе 567.
2. **H2:** Uncomment .env `PROXY_URL=socks5://...`
3. **H3 Windows local only:** `.\.venv\Scripts\python.exe -m playwright install --with-deps chromium` (1-shot install).

---

## T3. Telegram Bot `429 Too Many Requests: Retry-After: 42` (Flood Control TG)

### Симптом
```
docker compose logs worker -f
yupoo_worker  | ERROR    | telegram-service | API Request sendPhoto → HTTP 429 Too Many Requests: Retry-After: 42 seconds
yupoo_worker  | WARNING  | album-worker     | Sleeping 42 seconds per TelegramRetryAfter exception before retry.
```
Worker фактически стоит и не делает работу, если Retry-After > 300s часто. Фото не загружаются в TG CDN → `/media/image/{id}` отдаёт no-image placeholder.

### 3 гипотезы

#### H1 HIGH 80%: Worker interval слишком агрессивный (default compose 1.5s → 240 альбомов/час burst)
`docker-compose.yml:L67` command hardcoded `python scripts/run_worker.py --interval 1.5`. 1.5s между альбомами — слишком быстро для free-tier TG bot API лимит ~20 сообщений/мин + 30 МБ/фото = Retry-After.

#### H2 MEDIUM 18%: Одновременно запущено 2+ worker инстанса на 1 TG_TOKEN (double spend from swarm)
Kubernetes/Docker Swarm scale worker=2 или local worker + docker worker параллельно. Оба шлют 1 token = удвоение rate limit hit.

#### H3 LOW 2%: Фото альбомов > 100 files each (Telegram basic group limit)
Один альбом с 120 фото (batch sendMediaGroup) → превышен лимит групповой отправки TG 100 media за вызов.

### Фикс
1. **H1 raise interval:** Заменить compose L67 на `python scripts/run_worker.py --interval 5.0`. 5s → ~12 альбомов мин 720/час safe. Retry-After исчезнет. Cross-ref layer01 [TelegramService retry-after in TelegramService reference section](file:///C:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/reference.md).
2. **H2:** `docker compose up -d --scale worker=1` (enforce 1 instance only). NO local run + docker parallel for same TG_TOKEN.
3. **H3:** Альбомы > 100 изображений вручную разбить или настроить батч параметр `MEDIA_GROUP_MAX_SIZE` = 90 (env var future).

---

## T4. Alembic Migration Broken DAG: `FAILED: Can't locate revision identified by 'XXXX'`

### Симптом
```powershell
.\.venv\Scripts\python.exe -m alembic current
FAILED: Can't locate revision identified by 'deadbeef1234'

.\.venv\Scripts\python.exe -m alembic upgrade head
alembic.util.exc.CommandError: Target database is not up to date with the latest migration.
```
DB alembic_version table имеет номер ревизии, которой нет в `alembic/versions/` 4 файлов на диске (кто-то вручную удалил migration файл или выполнил SQL patch без Alembic).

### 3 гипотезы

#### H1 HIGH ~90%: Git checkout стёрт 5-ю новую миграцию или ручной SQL alter table без `alembic stamp`
Актуальный DAG VERBATIM из Alembic down_revision grep должен быть **линейный 4-шаговый цепочка без разрывов**:
```
6b2dcf147d3c (revision=ROOT, down_revision=None — initial migration create tables)
  ↓ fa672223429c down_revision='6b2dcf147d3c' (M2M refactor categories)
    ↓ be3675542bee down_revision='fa672223429c' (UQ constraint album+origin dedup images)
      ↓ a93f1c7d8b2e HEAD down_revision='be3675542bee' (pg_trgm extension + GIN trigram idx)
```
VERIFY DAG before ANY operation. Cross-ref: [Alembic DAG spec layer02 reference §2.3](file:///C:/Users/Void/Desktop/yupoo-parser/docs/02-database-and-storage/reference.md).

#### H2 MEDIUM ~8%: alembic.ini hardcoded sqlalchemy.url mismatch .env DB_PASSWORD
alembic.ini L61 **hardcoded localhost credentials**: `postgresql+asyncpg://postgres:postgres@localhost:5432/yupoo_db` — это ТОЛЬКО для local CI. В Production Docker необходимо переопределить через env var `SQLALCHEMY_URL` или патчить alembic/env.py runtime reader. Если .env сменил DB_PASSWORD=strong но ini всё ещё `postgres:postgres` → миграция пытается подключиться не с тем паролем → Can't locate (обёрнутая ошибка).

#### H3 LOW ~2%: Postgres `alembic_version` table corrupted manually через DBeaver update
Кто-то от руки `UPDATE alembic_version SET version_num = 'fake_hash'` DBeaver.

### Фикс
1. **H1 correct DAG verify:**
   ```powershell
   .\.venv\Scripts\python.exe -m alembic history --verbose
   # Expected output 4 lines: 6b2d → fa672 → be367 → a93f (head).
   ```
   Если есть разрыв (пропущен revision между down → up) → checkout нужный migration файл из Git history, затем `alembic stamp a93f1c7d8b2e` (fake stamp to HEAD if you 100% schema matches). **Backup БД ПЕРЕД stamp!**
2. **H2 ini mismatch:** Не редактируйте alembic.ini. Лучше добавить environment variable export `ALEMBIC_CONFIG=...` или использовать -x option при запуске. Env vars config loaded in [src/db/session.py builder](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/session.py).
3. **H3 manual stamp:** Если уверены, что схема соответствует a93f head → single command: `.\.venv\Scripts\python.exe -m alembic stamp a93f1c7d8b2e`

---

## T5. Frontend Production Bugs (Phase 4 regressions)

### Симптом 5A Search Bar Always-Open: desktop header search dropdown раскрыт и не закрывается после загрузки страницы. DevTools Console error: `Alpine Expression Error: searchLock is not defined Expression: "searchLock()"`.

### Симптом 5B PhotoSwipe zoom aspect кривой: клик по картинке альбома → PS open → изображение растянуто в квадрат 1000×1000 (aspect ratio broken, оригинал 1440×1920).

### Общие 3 гипотезы для 5A и 5B (оба — Phase4 lessons mirror)

#### H1 HIGH ~75%: Нарушен Script Order CRITICAL Protocol base.html L27-L32 (search bar 5A) или Нарушен Jinja block scope rule (PhotoSwipe 5B)
- Для 5A: base.html 4 скрипта идут НЕ в том порядке (alpine defer перед search defer). Correct [base.html:L27-L32](file:///C:/Users/Void/Desktop/yupoo-parser/templates/base.html#L27-L32): 1. search.js defer → 2. menu.js defer → 3. htmx 1.9.10 SYNC → 4. alpine 3.14.3 defer → 5. extra_scripts block.
- Для 5B: PhotoSwipe updatePswpAttributes IIFE вынесли в components/head.html include-файл вместо album.html extra_head ДО `<body>`. Jinja block scope rule НЕ переопределяет блоки внутри include → CSS PS не загрузился, атрибуты data-pswpWidth не обновились после onload. Correct [album.html:L29-L65](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L29-L65) extra_head.

#### H2 MEDIUM ~20%: CDN блокировки (Alpine/HTMX/Tailwind/Fonts не загрузились → blank page)
Пользователь RU zone без self-host рецепта — ERR_BLOCKED_BY_CLIENT / net::ERR_NAME_NOT_RESOLVED cdn.jsdelivr.net / unpkg.com / fonts.googleapis.com. Cross-ref [layer03 how-to R8 self-host all libs](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/how-to.md).

#### H3 LOW ~5%: Safari iOS 17 scroll lock race (search open → переключить вкладку → вернуться → scroll убежал)
Re-entrancy guard `_weLocked` убрали из order modal album.html. Guard позволяет двум scroll lock компонентам сосуществовать без сброса savedScrollY друг друга. Подробно о guard протоколе объяснение: [layer 03 explanation §2.3 `_weLocked` re-entrancy guard coexistence](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/explanation.md#23-alpine-314--htmx-1910-hybrid-разделение-ответственности).

### Фикс
1. **5A H1:** Revert script order back to base L27-L32 EXACT as listed. 2-minute fix 3 перестановки строк. Cross-ref [layer03 Critical Protocol Script Order explanation §2.2](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/explanation.md#22-jinja2-decomposition-protocol-phase4-block-scope-bugfix-кодифицирован).
2. **5B H1:** 2 строки: (а) Перенесите `{% block extra_head %} ... updatePswpAttributes IIFE ... {% endblock %}` **только в album.html root extends**, не в include. (б) Проверьте typeof guard every img: `onload="(typeof window.updatePswpAttributes === 'function') && window.updatePswpAttributes(this)"` VERBATIM на each gallery `<img>`. Detailed 3 diagnostics sequence: [layer03 how-to R5 PhotoSwipe aspect debug](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/how-to.md).
3. **5A/5B H2:** Apply self-host R8 recipe: download Alpine/HTMX/Tailwind/Inter/JetBrains Mono files locally → replace CDN href/src with /static/* local paths.
4. **5B H3 iOS scroll:** Restore `_weLocked` boolean guard pattern in order modal x-data [album.html:L69-L105](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L69-L105).

---

## T6. `/health` endpoint: `services.telegram_available = false` (TG integration failed)

### Симптом
```
curl http://localhost:8765/health
{
  "status": "ok",
  "templates_dir": "templates",
  "services": {
    "telegram_available": false,
    "media_available": true
  }
}
```
Жители РФ часто получают false без PROXY_URL: Roskomnadzor блокирует api.telegram.org TCP. Все фото отображаются `no-image.png` placeholder.

### 3 гипотезы

#### H1 HIGH ~70%: Отсутствует `PROXY_URL` socks5/http .env env var uncomment
RU хост не имеет прямого маршрута до Telegram Bot API DC. Без PROXY_URL → `ClientConnectorError Cannot connect to host api.telegram.org:443 ssl:True` lifespan create_app. TG сервис None fallback выставлен в lifespan: [main.py:L78-L85](file:///C:/Users/Void/Desktop/yupoo-parser/src/main.py#L78-L85).

#### H2 MEDIUM ~25%: Неверный TG_TOKEN формат или TG_CHAT_ID начинается НЕ с -100 для супергруппы
Токен формат `123456:ABCDEF...`. Чат/канал ID для альбомов в TG — **обязательно начинается с `-100` для public/private супергрупп и каналов** (not group basic id `-12345`). .env.example L13-L14 пример `-1000000000000`.

#### H3 LOW ~5%: TG Bot не добавлен в канал/супергруппу или нет admin permission publish messages
@BotFather /setjoingroups enabled → invite bot в TG albums channel → give admin Post Messages permission. Без прав sendMessage sendPhoto → 403 Forbidden lifespan startup self-test fails → telegram_available false.

### Фикс
1. **H1 RU zone mandatory proxy:** Uncomment .env.example L18:
   ```env
   PROXY_URL=socks5://user:password@your-residential-proxy.example.com:1080
   # или MTProto proxy http://127.0.0.1:10808 если local tg proxy
   ```
   Перезапуск: `docker compose restart web worker` (env vars reload).
2. **H2:** BotToken copy-paste fresh из @BotFather (не добавляйте лидирующие/трейлинг пробелы). CHAT_ID: перешлите любое сообщение из канала в @username_to_id_bot → получите `chat_id = -100XXXXXXXXXX` → в .env именно это значение.
3. **H3:** Откройте Telegram → ваш канал → Add Members → поищите `@YourBot_username` → Admin → Rights: ✔ Post messages. Save.
4. **Final verify:** Reload `/health` → services.telegram_available=true ✔. All images from TG via `/media/image/{id}` start serving real photo (no placeholder).

---

> **Общий Quick-Triage Checklist (перед звонком разработчику):**<br>1. `docker compose ps` → 3 healthy?<br>2. `http://<host>/health` → tg available?<br>3. .env 13 env keys присутствуют?<br>4. Last 100 log lines each container? `docker compose logs db --tail 100 ; logs web --tail 100 ; logs worker --tail 100`.
