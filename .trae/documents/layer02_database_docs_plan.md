# Layer 02 Database & Storage Documentation Implementation Plan

## Repository Research (Заключение исследования)

Исследованы ВСЕ исходные файлы слоя 02. Итоги (VERBATIM извлечено из кода — 0 выдуманных данных):

### Состав слоя (архитектурные факты):
1. **4 SQL-таблицы + 1 M2M association table** ([models.py](file:///c:/Users/Void/Desktop/yupoo-parser/src/db/models.py)):
   - `categories` — Adjacency List self-referencing (`parent_id` FK ↔ categories.id), M2M ↔ albums
   - `albums` — `original_title / clean_title (TEXT)`, `yupoo_url UNIQUE String(512)`, `status String(20) index (pending/processing/completed/error)`, timestamps server_default `now()`, onupdate
   - `images` — `album_id CASCADE FK`, `yupoo_origin_url TEXT`, `tg_file_id Optional String(255)`, `position int default 0`, `is_cover bool default False`, UniqueConstraint `(album_id, yupoo_origin_url)` = uq_images_album_origin
   - `album_category_association` (M2M) — Composite PK `(album_id, category_id)` → `ON DELETE CASCADE` FK ↔ albums/categories

2. **4 Alembic миграции (VERBATIM имена/порядок)** ([alembic/versions/](file:///c:/Users/Void/Desktop/yupoo-parser/alembic/versions/)):
   - `6b2dcf147d3c_initial_migration.py` — Base schema (categories/albums/images O2M categories → albums)
   - `a93f1c7d8b2e_add_pg_trgm_extension_and_idx_album_title_trgm_gin.py` — `CREATE EXTENSION IF NOT EXISTS pg_trgm` + `idx_album_title_trgm GIN USING gin (clean_title gin_trgm_ops)`
   - `be3675542bee_add_uq_images_album_origin_unique_.py` — UniqueConstraint images dedup
   - `fa672223429c_refactor_to_many_to_many_categories.py` — Удалён O2M `albums.category_id`, создан M2M `album_category_association` с composite PK CASCADE FK

3. **Session Management (sqlalchemy async + asyncpg)** ([session.py](file:///c:/Users/Void/Desktop/yupoo-parser/src/db/session.py)):
   - URL builder: `postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}` (env vars, NO single DATABASE_URL). Defaults: `postgres/postgres/localhost/5432/yupoo_db`
   - Engine pool: `pool_size=10, max_overflow=20 (суммарно 30 соединений), pool_pre_ping=False, pool_use_lifo=True, echo=False`
   - Session factory: `expire_on_commit=False, autoflush=False, class_=AsyncSession` (KISS — без лишних SELECT после commit)
   - FastAPI Depends: `get_db_session()` AsyncGenerator + `dispose_engine()` cleanup (вызывается в FastAPI lifespan shutdown)

4. **pg_trgm Триграммный Поисковый Слой** ([queries/search.py](file:///c:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py)):
   - Constants: `DEFAULT_SIMILARITY_THRESHOLD=0.3`, `SUGGEST_DEFAULT_THRESHOLD=0.2`, `DEFAULT_SEARCH_LIMIT=50`, `SUGGEST_DEFAULT_LIMIT=8`, `MIN_QUERY_LENGTH=2`, `SUGGEST_MIN_QUERY_LENGTH=3`
   - Functions: `search_albums(session, query_str, *, limit=50, threshold=0.3) -> list[AlbumSearchHit]` (pg `func.similarity`, order_by similarity DESC), `search_albums_suggest(...) -> list[dict]` (CTE top similarity + ROW_NUMBER() window cover join)
   - Query cleaner: `_clean_query` strip quotes, collapse spaces, truncate 200 chars

5. **DTO Слой schemas.py** — ВСЕ **dataclass** (НЕ Pydantic): `AlbumSearchHit / AlbumCard / BreadcrumbItem / PaginatedAlbums / AlbumDetail / CategoryMenuRow`

6. **Query Layer Public API** (helpers + albums + categories):
   - helpers: `_bulk_cover_ids()` (ROW_NUMBER() OVER partition_by album_id order by is_cover DESC/position ASC/id ASC → rn=1 cover), `_first_letter` (menu A-Z grouping), `_attach_covers_stmt`
   - albums: `get_album_detail` (selectinload images+categories, breadcrumbs path), `get_latest_albums_paginated` → **DEFAULT_PER_PAGE=24**
   - categories: `get_category_path` (while-loop parent_id adjacency list climb → BreadcrumbItem build "Главная → ..."), `get_all_categories_with_counts` (LEFT JOIN M2M group_by count)

7. **Docker Compose Infra** ([docker-compose.yml](file:///c:/Users/Void/Desktop/yupoo-parser/docker-compose.yml)):
   - `db`: postgres:15-alpine, container `yupoo_db`, **port mapping: HOST=5433 ↔ CONTAINER=5432** (CRITICAL для DBeaver: НЕ 5432!)
   - `shm_size=128mb`, volume: `postgres_data local driver` → `/var/lib/postgresql/data`
   - healthcheck: pg_isready interval 5s retries 10 start_period 10s
   - web/worker depends_on: db condition=service_healthy

8. **Missing facts для how-to (нужно явно указать в рецептах)**:
   - NO Alembic upgrade auto-start: `docker-compose.yml` web command — закомментирован автозапуск (L34-L39), сейчас только `uvicorn src.main:app` → Alembic нужно запускать ВРУЧНУЮ перед первым запуском ИЛИ раскомментировать строки.
   - НЕТ отдельного init_db.py скрипта: первый старт = `alembic upgrade head` + pg_trgm extension миграция создаёт автоматически.

---

## Files and Modules (Что меняем + Scope каждого файла)

### 3 output MD-файла (docs/02-database-and-storage/):
1. **[explanation.md](file:///c:/Users/Void/Desktop/yupoo-parser/docs/02-database-and-storage/explanation.md)** — переписать skeleton → 4 раздела архитектурных объяснений (c 15+ line-reference ссылками на models.py/session.py/search.py/alembic)
2. **[how-to.md](file:///c:/Users/Void/Desktop/yupoo-parser/docs/02-database-and-storage/how-to.md)** — переписать skeleton → **8 рецептов** (bash+SQL blocks, venv python, docker exec команды)
3. **[reference.md](file:///c:/Users/Void/Desktop/yupoo-parser/docs/02-database-and-storage/reference.md)** — переписать skeleton → **5 спецификаций-таблиц** (env vars, Alembic migration log, 4 таблицы+индексы, schemas dataclasses, query layer API signatures)

### Исходные read-only reference (НЕ ТРОГАТЬ):
- `src/db/models.py`, `src/db/session.py`, `src/db/queries/*.py`, `src/db/schemas.py`
- `alembic/versions/*.py`, `docker-compose.yml`

---

## Implementation Steps (Порядок написания — DEPENDENCY ORDER)

### Step 1: explanation.md (4 раздела Architecture Explanation)
1. **§1 ER-модель и Adjacency List Категорий + M2M с альбомами:**
   - Текстовая ER-диаграмма (4 сущности + связи)
   - CASCADE правила (images album_id → delete-orphan, association composite PK, categories parent → set null, subcategories delete-orphan)
   - Self-referencing categories: Adjacency List vs Nested Sets/Closure Table trade-offs (KISS: один while-loop для breadcrumbs — достаточно для 300-500 категорий; не нужно CTE LATERAL рекурсию)
   - Refactor O2M → M2M (миграция fa6722...): почему album может принадлежать 2+ бренд-категориям? Fallback 1 primary category для breadcrumbs.
   - Refs: models.py L10-L25, L27-L51, L52-L87, L88-L107

2. **§2 Album ↔ Image: каскадное удаление + dedup UniqueConstraint:**
   - `uq_images_album_origin` — защита от дубликата одного и того же Yupoo URL в рамках одного альбома при retry воркера (идемпотентность)
   - ROW_NUMBER() window is_cover DESC / position ASC / id ASC — выбор одной обложки на батч _bulk_cover_ids (single query вместо N+1)
   - Refs: models.py L90-L96, queries/helpers.py L32-L67

3. **§3 pg_trgm Триграммный поиск (вместо PG FTS/Elastic/Meilisearch):**
   - Почему триграммы а не tsvector/tsquery: нечёткий поиск (опечатки "jordans" / "jordns"), работает на мультиязычных clean_title (lat+digits артикулов), нулевая devops стоимость vs отдельный индекс-сервер
   - Как работает `similarity(trgm)`: триграммный пересекающийся индекс "nike air" → "nik ike ke ..." + `gin_trgm_ops` GIN
   - Два режима: полнотекстовый search_albums (threshold 0.3, top 50) + suggest выпадающий список (threshold 0.2, top 8, min 3 chars → меньше шума)
   - Refs: queries/search.py L13-L18, L21-L75, L78-L165, models.py L55-L60

4. **§4 Session Management + Connection Pool Lifetime:**
   - Async session pool 10+20 = 30 соединений (вместо 1 по умолчанию): нужно для 12 worker threads + FastAPI 8 uvicorn workers
   - `pool_use_lifo=True`: Last-In-First-Out — меньше «мертвых» idle соединений при низкой активности
   - `expire_on_commit=False`: NO extra SELECT → album_object.clean_title после session.commit() (в AlbumWorker critical, т.к. commit один в конце)
   - FastAPI lifespan: singleton engine/session factory get_session_factory, dispose_engine shutdown (утечек 0)
   - Refs: session.py L14-L62

### Step 2: how-to.md (8 рецептов, как в layer 01 — с готовыми bash/SQL командами Windows)
Общие prerequisites: `cd c:\Users\Void\Desktop\yupoo-parser`, venv python `.\\.venv\\Scripts\\python.exe`

1. **Рецепт 1: Первый запуск — Docker + Alembic init базы (с нуля):**
   - `docker compose up -d db` → wait healthy
   - Раскомментировать L34-L39 docker-compose.yml OR run руками:
     ```
     .\\.venv\\Scripts\\python.exe -m alembic upgrade head
     ```
   - Verify: `\dt` psql OR DBeaver таблицы

2. **Рецепт 2: Подключение DBeaver к Postgres 15-alpine (HOST=5433 ВАЖНО!):**
   - Параметры подключения: Host=localhost, Port=**5433** (не 5432!), Database=yupoo_db, Username/Password из .env
   - Проверка pg_trgm: `SELECT * FROM pg_extension WHERE extname='pg_trgm'`

3. **Рецепт 3: Валидация работы pg_trgm поиска (SQL EXPLAIN ANALYZE):**
   - SQL-блок теста: `SELECT id, clean_title, similarity(clean_title, 'air jordan') AS sim FROM albums WHERE similarity(clean_title, 'air jordan') > 0.3 ORDER BY sim DESC LIMIT 10;`
   - EXPLAIN ANALYZE должен показывать "Index Scan using idx_album_title_trgm" (НЕ Seq Scan!)
   - Если нет индекса → hand run миграции: `... alembic upgrade a93f1c7d8b2e`

4. **Рецепт 4: Создание новой миграции Alembic + накат:**
   - Изменяем models.py → `.\\.venv\\Scripts\\python.exe -m alembic revision --autogenerate -m "add column target_cover_idx"`
   - Ревью файла в alembic/versions/ → править downgrade
   - Накат: `.\\.venv\\Scripts\\python.exe -m alembic upgrade head`
   - Откат на 1: `.\\.venv\\Scripts\\python.exe -m alembic downgrade -1`

5. **Рецепт 5: Сброс «зависших» worker-задач (Album.status processing → pending):**
   - SQL-блок с параметром 30 минут: `UPDATE albums SET status='pending', updated_at=now() WHERE status='processing' AND updated_at < now() - INTERVAL '30 minutes';`
   - WITH affected count
   - Docker exec run: `docker exec -it yupoo_db psql -U postgres -d yupoo_db -c "..."`

6. **Рецепт 6: Полный backup (pg_dump custom format) + restore:**
   - Backup (docker exec из контейнера → ./backups/):
     ```
     docker exec yupoo_db pg_dump -U postgres -d yupoo_db -Fc -f /tmp/yupoo_$(Get-Date -Format "yyyyMMdd_HHmm").dump
     docker cp yupoo_db:/tmp/yupoo_*.dump .\backups\
     ```
   - Restore clean DB: drop/create DB → `pg_restore -U ... -d yupoo_db .\backups\x.dump`

7. **Рецепт 7: Проверка консистентности (orphan images, M2M dangling rows, zero images completed albums):**
   - 3 SQL-запроса-чека с выводом count:
     a. Orphan images: `SELECT count(*) FROM images i LEFT JOIN albums a ON i.album_id=a.id WHERE a.id IS NULL;` (0 — CASCADE должен был удалить)
     b. Dangling M2M: `SELECT count(*) FROM album_category_association aca LEFT JOIN albums a ON aca.album_id=a.id WHERE a.id IS NULL;`
     c. Completed albums with 0 images: `SELECT count(*) FROM albums a WHERE a.status='completed' AND 0=(SELECT count(*) FROM images i WHERE i.album_id=a.id);`
   - Если >0 → run fix

8. **Рецепт 8: Валидация health-check обложек (target_cover_idx sync ratio):**
   - SQL count без обложки is_cover: `SELECT count(*) FROM albums a WHERE status='completed' AND 0=(SELECT count(*) FROM images i WHERE i.album_id=a.id AND is_cover=true);`
   - Запуск fix_covers.py если >1% (см. layer 01 recipe 6)

### Step 3: reference.md (5 спецификаций-таблиц, 0 выдуманных значений — VERBATIM)
1. **§2.1 Переменные окружения БД (5 vars + defaults)**
   - Таблица: Env key / default / назначение / применяется в
   - DB_USER / DB_PASSWORD / DB_HOST / DB_PORT / DB_NAME
   - Defaults = postgres/postgres/localhost/5432/yupoo_db

2. **§2.2 Alembic Migration Log (4 миграции порядок)**
   - Таблица: Revision ID / Дата (извлекаем из файла created_at если есть → иначе порядок) / Имя / Описание schema change
   - 6b2d / a93f (pg_trgm + gin idx) / be3675 (uq_images) / fa6722 (M2M refactor)

3. **§2.3 Спецификация 4 таблиц PostgreSQL + indexes + constraints**
   - **categories** таблица колонка-за-колонкой (name type nullable default comment)
   - **albums** (status index, idx_album_title_trgm gin_trgm_ops GIN)
   - **images** (uq_images_album_origin UniqueConstraint)
   - **album_category_association** (composite PK CASCADE FK)
   - Отдельная сводная таблица всех индексов: Имя индекса / Таблица / Колонка / Метод (btree/gin) / Назначение

4. **§2.4 Спецификация schemas.py — DTO dataclasses (6 штук)**
   - Каждый dataclass: имя, поля (имя/тип/Optional/default если есть), возвращается из какой query-функции
   - AlbumSearchHit / AlbumCard / BreadcrumbItem / PaginatedAlbums / AlbumDetail / CategoryMenuRow

5. **§2.5 Query Layer Public API (12+ function сигнатур + return types VERBATIM)**
   - helpers: _clean_query, _first_letter, _bulk_cover_ids, _attach_covers_stmt
   - albums: DEFAULT_PER_PAGE=24, get_album_detail/ get_latest_albums/ get_latest_albums_paginated/ get_category_albums_paginated
   - categories: get_category_by_id/ get_category_path/ get_all_categories_with_counts
   - search: 6 constants table + search_albums/ search_albums_suggest
   - Session API: get_engine, get_session_factory, get_db_session, dispose_engine

---

## Dependencies and Considerations (Правила оформления — как Layer 01 для consistency):
1. **ZERO fabrications policy:** ВСЕ числовые константы (0.3 threshold, page size 24, pool 10/20), ИМЕНА ТАБЛИЦ/КОЛОНОК, ENV VAR keys — VERBATIM из кода. Никаких выдуманных "pool_timeout=300" если нет в session.py.
2. **Язык — профессиональный русский технический**, как в layer 01: одинаковые термины (воркер, pg_trgm, session factory, CASCADE, M2M, dataclass, alembic revision, gin_trgm_ops)
3. **Code Reference links во ВСЕХ 3 файлах:** каждая секция explanation имеет `file:///...` line-reference 1-2 строки ниже; таблицы reference имеют footer link "Код: session.py:L14-L20" style.
4. **Docker port mapping 5433:5432** — ОБЯЗАТЕЛЬНО во всех рецептах с DBeaver/pgAdmin! Частая ошибка "не могу подключиться к 5432" — пользователи забывают о маппинге.
5. **Alembic auto-start закомментирован по умолчанию**: В рецепте 1 ЯВНО указать "раскомментируй L34-L39 docker-compose.yml если хочешь авто-upgrade, иначе руками запусти alembic upgrade head перед первым стартом web/worker."
6. **schemas.py содержит dataclass**, НЕ pydantic BaseModel — В reference §2.4 это ВАЖНО указать (почему dataclass: DTO только read, нет необходимости в валидации, меньше зависимостей + быстрее).

---

## Validation (После написания трёх файлов — 6 проверок, как P7 в Layer 01):
1. **Grep CLI/env constants по docs/** → match реальному коду:
   - DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME defaults all 5 ✅
   - DEFAULT_SIMILARITY_THRESHOLD 0.3 / SUGGEST 0.2 / DEFAULT_PER_PAGE=24 / pool_size=10 max_overflow=20 / port=5433 ✅
2. **Имена всех 4 таблиц + 1 association + имена всех колонок** в reference §2.3 — 100% совпадение с models.py (написать bash/python скрипт/греп)
3. **Все public functions query layer** перечислены поименно в reference §2.5: 12+ функций — count совпадение с __all__ каждого queries/*.py
4. **Все 4 Alembic revision ID** в миграционном логе — grep `6b2dcf147d3c / a93f1c7d8b2e / be3675542bee / fa672223429c` — реально существуют в alembic/versions/.
5. **Все SQL-запросы how-to рецептов** — NO синтаксических ошибок (проверить table/column names match models)
6. **Code Reference links count:** ≥35 `file:///c:/Users/...` по 3 файлам суммарно.

---

## Risks and Handling (Риски):
1. **Риск 1: Fabricate env var DATABASE_URL (single URL string)** — в реальном коде НЕТ! Только 5 vars DB_*. **Mitigation:** validation §1 делает grep именно по 5 именам env.
2. **Риск 2: Забыть упомянуть port 5433 (host), указать 5432 (container internal)** — пользователь потом DBeaver подключиться не сможет. **Mitigation:** В recipe 2/6/7 docker exec commands ЯВНО прописать port, и в validation explicit grep.
3. **Риск 3: Alembic миграция M2M refactor fa672223429c — не описать почему (album может быть в 2 категориях одновременно)** — explanation будет неполным. **Mitigation:** Explanation §1 dedicated абзац.
4. **Риск 4: dataclass vs Pydantic mixup** — в schemas.py ВСЕ 6 DTO dataclass frozen? НЕТ frozen явно. **Mitigation:** Проверить @dataclass decorator lines в schemas.py; В reference указать "без валидации, только для передачи данных".
