# Справочник: Переменные окружения, миграции Alembic, схемы таблиц, DTO и Query API

Аннотация: Исчерпывающий технический справочник слоя «База данных и хранилище». Переменные окружения и конфигурация пула соединений, журнал всех 4 миграций Alembic с указанием upgrade/downgrade-операций, детальная спецификация 5 таблиц и 7 индексов/ограничений, 6 DTO dataclass из `schemas.py` с полным перечнем полей, а также сигнатуры всех публичных функций слоя запросов (`queries/*`) и session factory.

---

## § 2.1 Переменные окружения слоя БД

URL подключения к PostgreSQL **не считывается** из одной переменной `DATABASE_URL`, а собирается динамически из 5 отдельных переменных в функции `_build_database_url` — [session.py:L14-L22](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/session.py#L14-L22). Это позволяет независимо переопределять любой компонент в docker-compose или `.env`.

| Env Key | Default Value | Purpose | Used in |
|---------|---------------|---------|---------|
| `DB_USER` | `postgres` | Имя пользователя PostgreSQL (совпадает с `POSTGRES_USER` в контейнере) | `_build_database_url()` + `docker-compose.yml:L11` healthcheck pg_isready |
| `DB_PASSWORD` | `postgres` | Пароль пользователя PostgreSQL (совпадает с `POSTGRES_PASSWORD`) | `_build_database_url()` + `docker-compose.yml:L12` |
| `DB_HOST` | `localhost` | Хост экземпляра PostgreSQL; **в docker-compose сети** значение `db` (имя сервиса), локально — `localhost` | `_build_database_url()` |
| `DB_PORT` | `5432` | Внутренний порт PostgreSQL **внутри контейнера**. ВНИМАНИЕ: снаружи контейнера (DBeaver/pgAdmin на Windows-хосте) используй **`5433`** из Port Mapping | `_build_database_url()` + `docker-compose.yml:L15` `"5433:5432"` |
| `DB_NAME` | `yupoo_db` | Имя логической БД (совпадает с `POSTGRES_DB` контейнера) | `_build_database_url()` + `docker-compose.yml:L13` |

> **Критическое напоминание о Port Mapping:**
> Снаружи Docker Desktop (DBeaver, pgAdmin на Windows-хосте) PostgreSQL слушает **только** порт **`5433`** (см. [docker-compose.yml:L15](file:///C:/Users/Void/Desktop/yupoo-parser/docker-compose.yml#L15)). Значение `DB_PORT=5432` по умолчанию работает **только** внутри docker-сети (сервисы `web`/`worker`) или при прямом доступе в контейнер (`docker exec -it yupoo_db psql`).

Собранный формат финального URL (используется SQLAlchemy + asyncpg драйвер):
```
postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}
```

---

## § 2.2 Конфигурация пула соединений (Session Pool)

Параметры движка и фабрики сессий задаются в [session.py:L27-L50](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/session.py#L27-L50) и применяются глобально ко всему проекту:

| Параметр | Значение | Назначение |
|----------|----------|------------|
| `pool_size` | `10` | Базовый размер постоянного пула соединений |
| `max_overflow` | `20` | Временные дополнительные соединения сверх `pool_size` при всплесках. **Максимально суммарно: 30 одновременных соединений** (10 base + 20 overflow) |
| `pool_pre_ping` | `False` | Отключен для скорости на локальном PG; не нужна проверка живости соединения перед каждым запросом |
| `pool_use_lifo` | `True` | Last-In-First-Out выдача соединений: повторное использование самых «свежих», минимизирует переподключения при спадах нагрузки |
| `echo` | `False` | Логирование SQL-выражений в stdout отключено (включай только для отладки) |
| `expire_on_commit` | `False` | **Критично для AlbumWorker**: после commit ORM-объекты `Album`/`Image` остаются валидными без перевыборки (нет лишнего SELECT на критическом пути) |
| `autoflush` | `False` | Явное управление flush'ем сессии — только перед commit |
| Класс фабрики | `AsyncSession` | `async_sessionmaker[AsyncSession]` — всё взаимодействие с БД асинхронное |

---

## § 2.3 Журнал миграций Alembic (4 ревизии)

Все ревизии лежат в каталоге [alembic/versions/](file:///C:/Users/Void/Desktop/yupoo-parser/alembic/versions/). Порядок **применения** (Alembic DAG):
```
6b2dcf147d3c (initial) → fa672223429c (M2M) → be3675542bee (uq) → a93f1c7d8b2e (pg_trgm + GIN → HEAD)
```

| Revision ID | Filename | Upgrade Actions | Downgrade Actions |
|-------------|----------|-----------------|-------------------|
| `6b2dcf147d3c` (root) | `6b2dcf147d3c_initial_migration.py` | 1. `create_table categories` (id/name/yupoo_path unique/parent_id self-FK) <br> 2. `create_table albums` (id, **O2M category_id FK NOT NULL**, original/clean_title, yupoo_url unique, weidian_url nullable, status String(20), timestamps `server_default now()`) <br> 3. `create_index ix_albums_status` btree на `albums.status` <br> 4. `create_table images` (id, album_id FK CASCADE, yupoo_origin_url Text, tg_file_id nullable, position Int, is_cover Bool) | 1. `drop_table images` <br> 2. `drop_index ix_albums_status` с `albums` <br> 3. `drop_table albums` <br> 4. `drop_table categories` |
| `fa672223429c` | `fa672223429c_refactor_to_many_to_many_categories.py` | 1. `create_table album_category_association` — composite PK `(album_id, category_id)`, оба FK с `ON DELETE CASCADE` <br> 2. `add_column albums.cover_url` (`Text`, nullable) <br> 3. `drop_constraint albums_category_id_fkey` → `drop_column albums.category_id` (старое O2M убираем) <br> 4. Пересоздаём `categories.parent_id FK` с `ON DELETE SET NULL` (был RESTRICT) | 1. Дропаем новый parent FK → создаём обратно старый `categories_parent_id_fkey` (SET NULL снимаем) <br> 2. `add_column albums.category_id INTEGER NOT NULL` <br> 3. Создаём `albums_category_id_fkey` обратно (возвращаемся к O2M) <br> 4. `drop_column albums.cover_url` <br> 5. `drop_table album_category_association` |
| `be3675542bee` | `be3675542bee_add_uq_images_album_origin_unique_.py` | 1. `create_unique_constraint uq_images_album_origin` на таблице `images`, колонки `(album_id, yupoo_origin_url)` — дедупликация картинок при ретраях AlbumWorker | 1. `drop_constraint uq_images_album_origin` type=unique с `images` |
| **`a93f1c7d8b2e` (HEAD)** | `a93f1c7d8b2e_add_pg_trgm_extension_and_idx_album_title_trgm_gin.py` | 1. `CREATE EXTENSION IF NOT EXISTS pg_trgm` <br> 2. `create_index idx_album_title_trgm` — **GIN** на `albums.clean_title` с opclass `gin_trgm_ops` (триграммный нечёткий поиск) | 1. `drop_index idx_album_title_trgm` с `albums` <br> 2. `DROP EXTENSION IF EXISTS pg_trgm` |

---

## § 2.4 Спецификация таблиц PostgreSQL + индексы и ограничения

Все 5 таблиц (4 предметные + ассоциативная) объявлены в [models.py:L10-L107](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/models.py#L10-L107).

### § 2.4.1 Таблица `categories` — Adjacency List дерево категорий ([models.py:L27-L50](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/models.py#L27-L50))

| Колонка | Тип SQLAlchemy | PK | FK / Unique | Default | Nullable | Назначение |
|---------|---------------|----|-------------|---------|----------|------------|
| `id` | `Integer` | ✅ | — | autoincrement | ❌ | Первичный ключ категории |
| `name` | `String(255)` | — | — | — | ❌ | Читаемое имя категории (для меню и breadcrumbs) |
| `yupoo_path` | `String(512)` | — | **UNIQUE** constraint | — | ❌ | Уникальный путь категории на Yupoo CDN (используется в каталоге-оригинале) |
| `parent_id` | `Integer` | — | FK → `categories.id` `ON DELETE SET NULL` (после миграции fa6722) | — | ✅ | Родитель для Adjacency List; `NULL` = корневая категория |

**ORM-relationships:**
- `Category.subcategories` ↔ `Category.parent` (self-referential, `cascade="all, delete-orphan"`)
- `Category.albums` — M2M через `album_category_association`

---

### § 2.4.2 Таблица `albums` — карточки товаров/альбомов ([models.py:L52-L86](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/models.py#L52-L86))

| Колонка | Тип SQLAlchemy | PK | FK / Unique | Default | Nullable | Назначение |
|---------|---------------|----|-------------|---------|----------|------------|
| `id` | `Integer` | ✅ | — | autoincrement | ❌ | PK альбома |
| `original_title` | `Text` | — | — | — | ❌ | Сырое название с Yupoo (**Reseller Protection: никогда в шаблоны/JSON не выдавать**) |
| `clean_title` | `Text` | — | GIN индекс `idx_album_title_trgm` gin_trgm_ops | — | ❌ | Очищенное название (без размеров/таблиц/цен): **единственный** атрибут названия в HTTP-ответах |
| `yupoo_url` | `String(512)` | — | **UNIQUE** constraint | — | ❌ | Прямой URL альбома-источника на Yupoo |
| `weidian_url` | `Text` | — | — | — | ✅ | Опциональная ссылка на Weidian (**Reseller Protection: не выдавать наружу**) |
| `cover_url` | `Text` | — | — | — | ✅ | Кешированный hash-синхрон URL обложки (схема исправления обложек — [how-to.md §8](file:///C:/Users/Void/Desktop/yupoo-parser/docs/02-database-and-storage/how-to.md#-8-проверка-исправление-обложек-hash-синхрон-запустить-fix_covers)) |
| `status` | `String(20)` | — | btree индекс `ix_albums_status` | `"pending"` | ❌ | Статусы очереди `pending` → `processing` → `completed`/`failed` (состояние воркера) |
| `created_at` | `DateTime` | — | — | `server_default func.now()` | ❌ | Дата создания записи в БД |
| `updated_at` | `DateTime` | — | — | `server_default func.now()` + `onupdate=func.now()` | ❌ | Авто-дата последнего обновления записи (используется как sorting key ленты новинок) |

**ORM-relationships:**
- `Album.categories` — M2M через `album_category_association`
- `Album.images` — O2M на `Image`, `cascade="all, delete-orphan"` (удаляем альбом — удаляем все его картинки)

---

### § 2.4.3 Таблица `images` — элементы галереи альбома ([models.py:L88-L107](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/models.py#L88-L107))

| Колонка | Тип SQLAlchemy | PK | FK / Unique | Default | Nullable | Назначение |
|---------|---------------|----|-------------|---------|----------|------------|
| `id` | `Integer` | ✅ | — | autoincrement | ❌ | PK изображения (передаётся в image router CDN) |
| `album_id` | `Integer` | — | FK → `albums.id` `ON DELETE CASCADE`; **ч. composite UNIQUE `uq_images_album_origin`** | — | ❌ | Владелец-альбом; удаление альбома → каскад дроп картинок |
| `yupoo_origin_url` | `Text` | — | **вторая ч. `uq_images_album_origin` (album_id + yupoo_origin_url = unique)** | — | ❌ | Оригинальный URL картинки на CDN Yupoo (ключ идемпотентности при ретраях) |
| `tg_file_id` | `String(255)` | — | — | — | ✅ | `file_id` в Telegram CDN (получаем после `sendDocument`/`sendPhoto`; ключ стриминга без повторной выгрузки) |
| `position` | `Integer` | — | — | `0` | ❌ | Порядок отображения картинок в альбоме (используется в ROW_NUMBER для выбора обложки) |
| `is_cover` | `Boolean` | — | — | `False` | ❌ | Флаг целевой обложки (`target_cover_idx` из хеш-приоритета Yupoo) |

**Composite UniqueConstraint (idempotency):** `uq_images_album_origin(album_id, yupoo_origin_url)` — гарантия: один URL с Yupoo появляется в рамках альбома только 1 раз, даже если воркер перезапустился и повторяет загрузку.

---

### § 2.4.4 Таблица `album_category_association` — M2M линковка альбом ↔ категории ([models.py:L10-L25](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/models.py#L10-L25))

| Колонка | Тип | PK | FK | Nullable | Назначение |
|---------|-----|----|----|----------|------------|
| `album_id` | `Integer` | ✅ (ч. PK) | FK → `albums.id ON DELETE CASCADE` | ❌ | Ссылка на альбом; удаление альбома удаляет все связи |
| `category_id` | `Integer` | ✅ (ч. PK) | FK → `categories.id ON DELETE CASCADE` | ❌ | Ссылка на категорию; удаление категории удаляет все связи |

Composite Primary Key `(album_id, category_id)` автоматически гарантирует отсутствие дублей связей.

---

### § 2.4.5 Сводная таблица индексов и ограничений всего слоя

| Name | Table | Type | Column(s) / Expression | Назначение |
|------|-------|------|-----------------------|------------|
| `categories_pkey` | `categories` | PK btree | `id` | — |
| `uq_categories_yupoo_path` (UNIQUE) | `categories` | Unique btree | `yupoo_path` | Один путь Yupoo — одна категория |
| `categories_parent_id_fkey` | `categories` | FK (SET NULL) | `parent_id → categories.id` | Удаление родителя → подкатегории становятся корневыми |
| `albums_pkey` | `albums` | PK btree | `id` | — |
| `uq_albums_yupoo_url` (UNIQUE) | `albums` | Unique btree | `yupoo_url` | Один URL альбома Yupoo — одна запись |
| `ix_albums_status` (Alembic 6b2d) | `albums` | Plain btree | `status` | Быстрый фильтр очереди воркера по статусу |
| **`idx_album_title_trgm`** (Alembic a93f, **GIN**) | `albums` | **GIN индекс** opclass `gin_trgm_ops` | `clean_title` | Триграммный нечёткий поиск `similarity()` (Bitmap Index Scan ~1-3 мс) |
| `images_pkey` | `images` | PK btree | `id` | — |
| `images_album_id_fkey` | `images` | FK (CASCADE) | `album_id → albums.id` | — |
| **`uq_images_album_origin`** (Alembic be367) | `images` | Composite Unique btree | `(album_id, yupoo_origin_url)` | Ключ идемпотентности загрузок картинок |
| `album_category_association_pkey` (Alembic fa672) | `album_category_association` | Composite PK btree | `(album_id, category_id)` | Детерминированная M2M-связь |
| `album_category_association_album_id_fkey` | ассоциация | FK (CASCADE) | `album_id → albums.id` | — |
| `album_category_association_category_id_fkey` | ассоциация | FK (CASCADE) | `category_id → categories.id` | — |

---

## § 2.5 DTO-схемы (`schemas.py`) — 6 dataclass (не Pydantic)

Все транспортные модели — чистые `@dataclass` Python без валидации и зависимостей BaseModel. Экспортируются через `__all__` в [schemas.py:L63-L70](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/schemas.py#L63-L70).

### § 2.5.1 `AlbumSearchHit` (результат полноценного поиска)
([schemas.py:L10-L15](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/schemas.py#L10-L15))
Возвращается из: `search_albums()` → [queries/search.py:L21-L75](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L21-L75)

| Поле | Тип | Optional | Default | Назначение |
|------|-----|----------|---------|------------|
| `album` | `Album` (ORM объект) | ❌ | — | Полный ORM-инстанс альбома для детальной отрисовки результатов |
| `similarity` | `float` | ❌ | — | Степень схожести по триграммам (0.0–1.0, порог по умолчанию `> 0.3`) |
| `cover_image_id` | `int` | ✅ | `None` | `id` выбранной обложки (из `_bulk_cover_ids` batch-запроса) |
| `cover_tg_file_id` | `str` | ✅ | `None` | Зарезервировано: прямой Telegram `file_id` обложки |

---

### § 2.5.2 `AlbumCard` (элемент сетки каталога)
([schemas.py:L18-L22](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/schemas.py#L18-L22))
Возвращается из: `get_latest_albums`, `get_latest_albums_paginated`, `get_category_albums_paginated` → [queries/albums.py](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py)

| Поле | Тип | Optional | Default | Назначение |
|------|-----|----------|---------|------------|
| `album_id` | `int` | ❌ | — | PK альбома; формирует ссылку `/album/{id}` |
| `clean_title` | `str` | ❌ | — | Очищенное название — **единственный** текст на карточке (Reseller Protection) |
| `cover_image_id` | `int` | ✅ | — | `id` обложки; идёт в `GET /image/{id}` CDN роутера |

---

### § 2.5.3 `BreadcrumbItem` (хлебная крошка)
([schemas.py:L25-L29](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/schemas.py#L25-L29))
Возвращается из: `get_category_path()` ([queries/categories.py:L24-L41](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/categories.py#L24-L41)); встраивается в `AlbumDetail.breadcrumbs`.

| Поле | Тип | Optional | Default | Назначение |
|------|-----|----------|---------|------------|
| `id` | `int` | ✅ (Nullable) | — | `id` категории; `None` = фиксированная крошка «Главная» |
| `name` | `str` | ❌ | — | Текст крошки (название категории / чистый заголовок альбома) |
| `url` | `str` | ❌ | — | Относительный URL крошки: `/`, `/category/{id}`, `/album/{id}` |

---

### § 2.5.4 `PaginatedAlbums` (пагинация списка карточек)
([schemas.py:L32-L42](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/schemas.py#L32-L42))
Возвращается из: `get_latest_albums_paginated`, `get_category_albums_paginated` → [queries/albums.py:L109-L235](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py#L109-L235). Используется HTMX Infinite Scroll.

| Поле | Тип | Optional | Default | Назначение |
|------|-----|----------|---------|------------|
| `items` | `list[AlbumCard]` | ❌ | — | Список карточек текущей страницы |
| `page` | `int` | ❌ | — | Номер страницы (1-based) |
| `per_page` | `int` | ❌ | — | Размер страницы; по умолчанию `DEFAULT_PER_PAGE = 24` |
| `total` | `int` | ❌ | — | Всего альбомов в выборке (COUNT) |
| `total_pages` | `int` | ❌ | — | Всего страниц: `ceil(total / per_page)` |
| `has_prev` | `bool` | ❌ | — | Есть предыдущая страница: `page > 1` |
| `has_next` | `bool` | ❌ | — | Есть следующая страница: `page < total_pages` |
| `prev_url` | `str` | ✅ | `None` | Зарезервировано для HTMX next-page URL |
| `next_url` | `str` | ✅ | `None` | Зарезервировано для HTMX next-page URL |

---

### § 2.5.5 `AlbumDetail` (детальная страница альбома)
([schemas.py:L45-L51](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/schemas.py#L45-L51))
Возвращается из: `get_album_detail()` ([queries/albums.py:L20-L77](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py#L20-L77))

| Поле | Тип | Optional | Default | Назначение |
|------|-----|----------|---------|------------|
| `album_id` | `int` | ❌ | — | PK альбома |
| `clean_title` | `str` | ❌ | — | Очищенный заголовок `<h1>` страницы |
| `cover_image_id` | `int` | ✅ | — | Hero-обложка страницы |
| `images` | `List[int]` | ❌ | — | Список `id` всех картинок альбома в порядке `position → id` (индексируется PhotoSwipe v5) |
| `breadcrumbs` | `List[BreadcrumbItem]` | ❌ | — | Цепочка «Главная → … → Категория → Альбом» |

---

### § 2.5.6 `CategoryMenuRow` (пункт меню категорий с A-Z группировкой)
([schemas.py:L54-L60](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/schemas.py#L54-L60))
Возвращается из: `get_all_categories_with_counts()` ([queries/categories.py:L43-L82](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/categories.py#L43-L82))

| Поле | Тип | Optional | Default | Назначение |
|------|-----|----------|---------|------------|
| `id` | `int` | ❌ | — | PK категории; формирует ссылку `/category/{id}` |
| `name` | `str` | ❌ | — | Название категории для отображения |
| `first_letter` | `str` | ❌ | — | A-Z / `0–9` / `#` (из `_first_letter`) — ключ группировки меню [queries/helpers.py:L20-L29](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/helpers.py#L20-L29) |
| `album_count` | `int` | ❌ | — | Счётчик альбомов (LEFT JOIN M2M + GROUP BY COUNT) |
| `url` | `str` | ❌ | — | Относительный URL `/category/{id}` |

---

## § 2.6 Query Layer: публичные сигнатуры + константы поиска

Разделение ответственности по 4 модулям:
- **Session/Engine lifecycle** → [session.py](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/session.py)
- **Общие хелперы запросов (batch-обложки, очистка query, A-Z буквы)** → [queries/helpers.py](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/helpers.py)
- **Запросы альбомов (детали/новинки/пагинация/категория)** → [queries/albums.py](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py)
- **Запросы категорий (by_id / path / menu)** → [queries/categories.py](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/categories.py)
- **Поиск триграммный (results / suggest)** → [queries/search.py](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py)

### § 2.6.1 Константы поиска и пагинации

| Константа | Значение по умолчанию | Модуль / строка | Применение |
|-----------|-----------------------|-----------------|------------|
| `DEFAULT_SIMILARITY_THRESHOLD` | `0.3` | [search.py:L13](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L13) | Минимальная триграммная схожесть в `search_albums()` (нижняя граница выдачи) |
| `SUGGEST_DEFAULT_THRESHOLD` | `0.2` | [search.py:L18](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L18) | Порог для dropdown-подсказок search_suggest (ниже — шире подсказки) |
| `DEFAULT_SEARCH_LIMIT` | `50` | [search.py:L14](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L14) | Максимальный размер результатов полной страницы поиска |
| `SUGGEST_DEFAULT_LIMIT` | `8` | [search.py:L16](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L16) | Максимальное количество пунктов dropdown (mobile-friendly) |
| `MIN_QUERY_LENGTH` | `2` | [search.py:L15](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L15) | Минимальная длина запроса для `search_albums` (ниже — пустой ответ) |
| `SUGGEST_MIN_QUERY_LENGTH` | `3` | [search.py:L17](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L17) | Минимальная длина запроса для suggest (ещё более строгий: 1-2 символа в UI не триггерят сетевой запрос) |
| **`DEFAULT_PER_PAGE`** | **`24`** | [albums.py:L17](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py#L17) | Размер страницы для карточек в каталоге; 24 = 6 рядов grid-cols-2 × 4 ряда grid-cols-3 на десктопе |

---

### § 2.6.2 Session Factory Lifecycle API

| Функция | Сигнатура | Возвращает | Строка в session.py | Назначение |
|---------|-----------|------------|---------------------|------------|
| `get_engine` | `get_engine() -> AsyncEngine` | `AsyncEngine` (singleton) | [L27-L39](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/session.py#L27-L39) | Лениво создаёт движок ровно 1 раз с параметрами пула §2.2 |
| `get_session_factory` | `get_session_factory() -> async_sessionmaker[AsyncSession]` | Готовая фабрика (singleton) | [L41-L50](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/session.py#L41-L50) | Фабрика с `expire_on_commit=False`, `autoflush=False` |
| `get_db_session` | `async def get_db_session() -> AsyncGenerator[AsyncSession, None]` | `AsyncGenerator` → одна `AsyncSession` на вызов | [L52-L55](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/session.py#L52-L55) | FastAPI dependency injection: `Depends(get_db_session)` — закрывает сессию при выходе из контекста |
| `dispose_engine` | `async def dispose_engine() -> None` | `None` | [L57-L62](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/session.py#L57-L62) | Lifespan shutdown: закрывает все соединения в пуле, сбрасывает singleton-ы engine и factory |

---

### § 2.6.3 Хелперы `queries/helpers.py` — batch-обложки и утилиты

| Функция / Символ | Сигнатура | Возвращает | Строка | Назначение |
|-----------------|-----------|------------|--------|------------|
| `_clean_query` | `_clean_query(raw: str) -> str` | `str` (max 200 chars) | [L10-L17](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/helpers.py#L10-L17) | Sanitize входа поиска: strip, удаляет кавычки `'"``\``, коллапсирует пробелы, обрезает до 200 символов (защита от инъекций в similarity op) |
| `_first_letter` | `_first_letter(name: str) -> str` | `str` ∈ {A-Z, `0–9`, `#`} | [L20-L29](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/helpers.py#L20-L29) | Первая буква имени категории для A-Z-группировки бокового меню |
| `_attach_covers_stmt` | `_attach_covers_stmt(album_ids: list[int]) -> Select` | SQLAlchemy `Select` (CTE-like) | [L32-L51](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/helpers.py#L32-L51) | ROW_NUMBER окно partition by album_id, priority: `is_cover DESC → position ASC → id ASC`; только rn=1. Детерминированный выбор обложки батчем |
| `_bulk_cover_ids` | `async def _bulk_cover_ids(session: AsyncSession, album_ids: list[int]) -> dict[int, int]` | `{album_id: cover_image_id}` (пустой dict при пустом вводе) | [L54-L67](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/helpers.py#L54-L67) | **Критичен для производительности**: один roundtrip в БД вместо N+1 SELECT обложек на странице из 24 карточек. Основной потребитель — все функции пагинации альбомов |

---

### § 2.6.4 Запросы альбомов `queries/albums.py`

| Функция | Сигнатура | Возвращает | Строка | Назначение |
|---------|-----------|------------|--------|------------|
| `get_album_detail` | `async def get_album_detail(session: AsyncSession, album_id: int) -> Optional[AlbumDetail]` | `AlbumDetail` или `None` если нет / DB error | [L20-L77](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py#L20-L77) | Детальная страница альбома: `selectinload` images + категории (2 запроса EAGER вместо 1+N), сортировка картинок и breadcrumbs по 1й категории |
| `get_latest_albums` | `async def get_latest_albums(session: AsyncSession, limit: int = 24, *, status_filter: Optional[str] = "completed") -> list[AlbumCard]` | `list[AlbumCard]` | [L80-L106](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py#L80-L106) | Плоский список последних обновлённых альбомов; `limit` clamp: `[1..120]`. Сортировка `updated_at DESC, id DESC` |
| `get_latest_albums_paginated` | `async def get_latest_albums_paginated(session: AsyncSession, page: int = 1, per_page: int = DEFAULT_PER_PAGE, *, status_filter: Optional[str] = "completed") -> PaginatedAlbums` | `PaginatedAlbums` | [L109-L163](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py#L109-L163) | Пагинация главной страницы ленты новинок. 2 roundtrip: COUNT + LIMIT/OFFSET с батчем обложек |
| `get_category_albums_paginated` | `async def get_category_albums_paginated(session: AsyncSession, category_id: int, page: int = 1, per_page: int = DEFAULT_PER_PAGE, *, status_filter: Optional[str] = "completed") -> PaginatedAlbums` | `PaginatedAlbums` | [L166-L235](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/albums.py#L166-L235) | Пагинация страницы категории. JOIN M2M association table; per_page clamp `[1..96]` |

---

### § 2.6.5 Запросы категорий `queries/categories.py`

| Функция | Сигнатура | Возвращает | Строка | Назначение |
|---------|-----------|------------|--------|------------|
| `get_category_by_id` | `async def get_category_by_id(session: AsyncSession, category_id: int) -> Optional[Category]` | ORM `Category` или `None` | [L14-L21](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/categories.py#L14-L21) | Ленивая выборка категории если нужно ORM-объект |
| `get_category_path` | `async def get_category_path(session: AsyncSession, category_id: int) -> List[BreadcrumbItem]` | `List[BreadcrumbItem]` — всегда начинается с Главной (`id=None`) | [L24-L41](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/categories.py#L24-L41) | Цикл while по `parent_id` (Adjacency List climb): 1 SELECT на уровень глубины; достаточно 2-3 запроса при 2-3 уровнях каталога |
| `get_all_categories_with_counts` | `async def get_all_categories_with_counts(session: AsyncSession) -> list[CategoryMenuRow]` | `list[CategoryMenuRow]` — A-Z отсортировано по name | [L43-L82](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/categories.py#L43-L82) | LEFT JOIN M2M + GROUP BY COUNT, вычисляется `first_letter` для A-Z-группировки меню в sidebar (1 запрос) |

---

### § 2.6.6 Триграммный поиск `queries/search.py`

| Функция / Символ | Сигнатура | Возвращает | Строка | Назначение |
|-----------------|-----------|------------|--------|------------|
| `search_albums` | `async def search_albums(session: AsyncSession, query_str: str, *, limit: int = DEFAULT_SEARCH_LIMIT, threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> list[AlbumSearchHit]` | `list[AlbumSearchHit]` (пустой при `< MIN_QUERY_LENGTH`) | [L21-L75](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L21-L75) | Полноценный поиск с рейтингом: `func.similarity(Album.clean_title, q) > real_threshold`, ORDER BY similarity DESC + `_bulk_cover_ids` post-join для обложек |
| `search_albums_suggest` | `async def search_albums_suggest(session: AsyncSession, query_str: str, *, limit: int = SUGGEST_DEFAULT_LIMIT, threshold: float = SUGGEST_DEFAULT_THRESHOLD) -> list[dict]` | `list[dict]` вида `{"id":int, "title":str, "image_id":int, "url":str}` — 4 поля, минимальный JSON payload | [L78-L165](file:///C:/Users/Void/Desktop/yupoo-parser/src/db/queries/search.py#L78-L165) | Dropdown-подсказки (1 roundtrip!): CTE `top` (top-N по similarity) LEFT OUTER JOIN `img_ranked` (ROW_NUMBER окно обложек) — без N+1, без второго запроса. Минимальный порог `≥ SUGGEST_MIN_QUERY_LENGTH = 3` |
