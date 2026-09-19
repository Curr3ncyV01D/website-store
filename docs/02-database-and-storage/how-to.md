# Практическое руководство: Инициализация, миграции Alembic, DBeaver, backup и проверки консистентности

Аннотация: Пошаговые практические рецепты для Windows (PowerShell): первый старт базы с нуля (docker-compose + Alembic), подключение админки DBeaver с учётом **port mapping HOST=5433**, проверка pg_trgm индекса через EXPLAIN ANALYZE, создание/откат миграций, сброс зависших worker-задач, дампы pg_dump custom format и 3 SQL-запроса проверки консистентности (orphan rows, dangling M2M, zero-images completed альбомы).

---

## Общие пререквизиты для ВСЕХ рецептов

Выполнить **ДО** запуска любых команд ниже:
```powershell
cd c:\Users\Void\Desktop\yupoo-parser
mkdir -Force .\backups  # для дампов базы (recipe 6)
```

Использовать интерпретатор **только из venv** (в system python нет `alembic`, `python-dotenv`, `asyncpg`):
```
.\\.venv\\Scripts\\python.exe -m alembic  <args>    # для миграций
.\\.venv\\Scripts\\python.exe scripts\\*.py          # для layer01 скриптов
```

Переменные из `.env` (пример значений):
```dotenv
# (.env) — реальные значения в проекте
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost        # локальная разработка; в контейнере заменить на "db"
DB_PORT=5432             # container internal (ignore local, см. DBeaver port=5433)
DB_NAME=yupoo_db
```

---

## Рецепт 1. Первый старт: Docker Postgres + Alembic init с нуля (с 0 до 4 таблиц)

**Проблема:** старый скелет docker-compose.yml имеет **автозапуск Alembic закомментирован по умолчанию** (L34-L39) — web/worker контейнеры упадут с ошибкой «relation «albums» does not exist».

### Шаги (Windows Localhost):
1. **Поднять только `db` контейнер** (сначала healthcheck healthy):
   ```powershell
   docker compose up -d db
   # ждать 10-30 секунд пока healthcheck=healthy:
   docker compose ps
   ```
   Ожидаемый вывод: `yupoo_db   postgres:15-alpine   Up (healthy)   0.0.0.0:5433->5432/tcp`.

2. **Накатить ВСЕ 4 миграции Alembic head** (создать схему + pg_trgm extension + unique constraint + M2M refactor):
   ```powershell
   .\\.venv\\Scripts\\python.exe -m alembic upgrade head
   ```
   Ожидаемый лог:
   ```
   INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
   INFO  [alembic.runtime.migration] Will assume transactional DDL.
   INFO  [alembic.runtime.migration] Running upgrade  -> 6b2dcf147d3c, initial_migration
   INFO  [alembic.runtime.migration] Running upgrade 6b2dcf147d3c -> a93f1c7d8b2e, add pg_trgm extension and idx_album_title_trgm gin
   INFO  [alembic.runtime.migration] Running upgrade a93f1c7d8b2e -> be3675542bee, add uq_images_album_origin unique constraint
   INFO  [alembic.runtime.migration] Running upgrade be3675542bee -> fa672223429c, refactor to many to many categories
   ```

3. **Опционально: включить автозапуск Alembic при старте web** (чтобы не повторять шаг 2 после wipe):
   - Открыть [docker-compose.yml:L34-L39](file:///c:/Users/Void/Desktop/yupoo-parser/docker-compose.yml#L34-L39)
   - Закомментировать одинарный `command: uvicorn ...` (L40)
   - Раскомментировать многострочный `command: > bash -c "alembic upgrade head || true ; uvicorn ..."` (L35-L39)

4. **Поднять весь стек** (web + worker):
   ```powershell
   docker compose up -d web worker
   ```

5. **Валидация:**
   ```powershell
   docker exec -it yupoo_db psql -U postgres -d yupoo_db -c "\dt"
   ```
   Должны быть **5 таблиц**: `alembic_version`, `album_category_association`, `albums`, `categories`, `images`.

---

## Рецепт 2. Подключение DBeaver к Postgres (HOST=5433 — ВАЖНО!)

**Частая ошибка №1:** подключение к порту **5432** (container-internal, закрыт на хосте) → ошибка «Connection refused».

**Порт на HOST Windows = 5433** (docker-compose port mapping `5433:5432`).

### Параметры подключения DBeaver 24+:
| Параметр | Значение | Комментарий |
|---|---|---|
| Тип БД | **PostgreSQL** | Драйвер скачать автоматически при первом подключении |
| Host | `localhost` или `127.0.0.1` | |
| **Port** | **`5433`** (НЕ 5432!) | docker-compose.yml mapping |
| Database | `yupoo_db` | соответствует DB_NAME из .env |
| Username | из `.env` DB_USER (default: `postgres`) | |
| Password | из `.env` DB_PASSWORD (default: `postgres`) | |
| Show all databases | ❌ отключить | |

### Тест 1: Проверка расширения pg_trgm
В DBeaver открыть SQL Editor → запустить:
```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'pg_trgm';
```
Ожидаемый результат: 1 строка `pg_trgm | 1.6` (или выше, в зависимости от PG 15 build).

### Тест 2: Проверка всех Alembic миграций накатились
```sql
SELECT version_num FROM alembic_version;
```
Ожидаемый: **`fa672223429c`** (последняя M2M-рефактор миграция).

---

## Рецепт 3. Валидация pg_trgm GIN-индекса: NO Seq Scan!

**Цель:** убедиться что запрос `WHERE similarity(clean_title, $1) > $2` использует **GIN Index** а не полный seq scan (50мс → 5мс разница).

### Шаг 1: Seed тестовых данных (если пустая база) — запустить layer01 discovery:
```powershell
.\\.venv\\Scripts\\python.exe scripts\\run_discovery.py
.\\.venv\\Scripts\\python.exe scripts\\run_crawler.py --limit-categories 3 --page-size-hint 120
```
Должно появиться 100+ альбомов в `albums` таблице.

### Шаг 2: EXPLAIN ANALYZE similarity search
В DBeaver SQL Editor выполнить:
```sql
EXPLAIN ANALYZE
SELECT
  id, clean_title,
  round(similarity(clean_title, 'air jordan')::numeric, 3) AS sim
FROM albums
WHERE similarity(clean_title, 'air jordan') > 0.3
ORDER BY sim DESC
LIMIT 10;
```

### ✅ PASS — строки вывода плана содержат:
```
->  Bitmap Heap Scan on albums
      Recheck Cond: (similarity((clean_title)::text, 'air jordan'::text) > 0.3::double precision)
        ->  Bitmap Index Scan on idx_album_title_trgm    <-- ГЛАВНОЕ! ИНДЕКС ИСПОЛЬЗУЕТСЯ
              Index Cond: ((clean_title)::text % 'air jordan'::text)
Planning Time: ... ms
Execution Time: 3.0-10.0 ms   <-- 5мс = НОРМА
```

### ❌ FAIL — что делать если **Seq Scan** вместо Bitmap Index:
1. В таблице <100 альбомов — PG optimizer предпочитает seq scan (дешевле). Добавляем 500+ альбомов crawler.
2. Отсутствует операторный класс `gin_trgm_ops` — руками накатить миграцию:
   ```powershell
   .\\.venv\\Scripts\\python.exe -m alembic upgrade a93f1c7d8b2e
   ```
3. Запустить `ANALYZE albums;` (обновить статистику planner):
   ```sql
   ANALYZE VERBOSE albums;
   ```

---

## Рецепт 4. Создание новой миграции Alembic + накат + откат

### Шаг 1: Изменить models.py (пример)
Добавить новый столбец в `Album` модель, например поле «артикул»:
```python
# src/db/models.py class Album (пример изменения)
sku: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
```

### Шаг 2: Сгенерировать --autogenerate миграцию
```powershell
.\\.venv\\Scripts\\python.exe -m alembic revision --autogenerate -m "add sku to albums"
```
Результат: создан новый файл в `alembic/versions/1234abcd5678_add_sku_to_albums.py`

### Шаг 3: **ОБЯЗАТЕЛЬНЫЙ REVIEW миграции!**
Открыть созданный файл:
- Проверить что `upgrade()` содержит `op.add_column('albums', sa.Column('sku', ...))`
- Проверить что `downgrade()` содержит `op.drop_column('albums', 'sku')` — **autogenerate часто забывает downgrade**
- **Критично:** добавить вручную транзакционные операции (CREATE EXTENSION, CONCURRENTLY индексы не трогать — добавлять отдельно руками)

### Шаг 4: Накатить миграцию
```powershell
.\\.venv\\Scripts\\python.exe -m alembic upgrade head
```

### Шаг 5: Откат на 1 миграцию назад (если нужно откатить sku):
```powershell
.\\.venv\\Scripts\\python.exe -m alembic downgrade -1
```

### Полезные команды Alembic:
```powershell
# Показать текущую применённую миграцию
.\\.venv\\Scripts\\python.exe -m alembic current

# Показать граф всех миграций (down/up dependencies)
.\\.venv\\Scripts\\python.exe -m alembic heads

# Показать SQL скрипт без выполнения (--sql dry-run)
.\\.venv\\Scripts\\python.exe -m alembic upgrade head --sql
```

---

## Рецепт 5. Сброс «зависших» worker-задач processing→pending

Когда происходит аварийное завершение worker (Ctrl+C, kill, ОЗУ out-of-memory), часть альбомов остаётся в статусе `processing` ВЕЧНО — воркеры их пропускают (выбирают только `pending`).

### 5.1 SQL-запрос сброса (через DBeaver SQL Editor):
```sql
-- Обрабатываем альбомы «зависшие» >30 минут с момента последнего обновления updated_at
-- Период выбирай с учётом: 1 альбом ~ 1.5-3 минуты при 8 фото + retry Telegram
WITH affected AS (
  UPDATE albums
  SET status       = 'pending',
      updated_at   = now()
  WHERE status = 'processing'
    AND updated_at < now() - INTERVAL '30 minutes'
  RETURNING id
)
SELECT count(*) AS reset_pending_albums FROM affected;
```

### 5.2 Сброс через docker exec (без DBeaver):
```powershell
docker exec -it yupoo_db psql `
  -U postgres `
  -d yupoo_db `
  -c "WITH a AS (UPDATE albums SET status='pending',updated_at=now() WHERE status='processing' AND updated_at < now()-INTERVAL '30 min' RETURNING id) SELECT count(*) FROM a;"
```

### 5.3 Сброс всех processing (аварийный wipe всего пула):
```sql
-- НЕ ИСПОЛЬЗУЙ ЕСЛИ ХОТЬ 1 ВОРКЕР АКТИВЕН! Перезапишет его живой транзакции → дубликаты
UPDATE albums SET status='pending', updated_at=now() WHERE status='processing';
```

---

## Рецепт 6. Полный Backup и Restore базы (pg_dump custom -Fc формат)

Custom binary формат `-Fc` = сжатый (лучше SQL plain text), поддерживает parallel restore `pg_restore -j 4`.

### 6.1 Backup (создать дамп из docker-контейнера → local .\backups\)
```powershell
# 1. Создать дамп ВНУТРИ контейнера во временный /tmp
$ts = Get-Date -Format "yyyyMMdd_HHmm"
$dumpName = "yupoo_$ts.dump"

docker exec yupoo_db pg_dump -U postgres -d yupoo_db -Fc -f "/tmp/$dumpName"
Write-Host "Created inside container: /tmp/$dumpName"

# 2. Копировать из контейнера на HOST в папку .\backups\
docker cp "yupoo_db:/tmp/$dumpName" ".\backups\$dumpName"
Get-Item ".\backups\$dumpName" | Select-Object Name, Length, LastWriteTime
```

Ожидаемый размер дампа: 30k альбомов × 240k изображений ≈ **150–300 МБ** сжатого.

### 6.2 Restore (чистая БД):
```powershell
# 1. Удалить старую БД + создать пустую (если нужно)
docker exec -it yupoo_db dropdb -U postgres --if-exists yupoo_db
docker exec -it yupoo_db createdb -U postgres yupoo_db

# 2. Скопировать дамп ОБРАТНО в контейнер tmp
$latestDump = Get-ChildItem .\backups\*.dump | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty Name
docker cp ".\backups\$latestDump" "yupoo_db:/tmp/restore.dump"

# 3. Восстановить -Fc формат
docker exec yupoo_db pg_restore -U postgres -d yupoo_db --no-owner --no-privileges -j 2 "/tmp/restore.dump"
```

---

## Рецепт 7. Проверка консистентности: 3 SQL-запроса healthcheck

Запускать **1 раз в день** cron или вручную после любого ручного редактирования БД. Результат **ИДЕАЛ = 0** по всем 3 запросам.

```sql
-- =============================================
-- 7.1 Orphan images = изображения без родителя альбома
--     Причина: ручной DELETE albums без CASCADE (должно быть 0 — FK CASCADE)
-- =============================================
SELECT count(*) AS orphan_images_count
FROM images i
LEFT JOIN albums a ON i.album_id = a.id
WHERE a.id IS NULL;

-- =============================================
-- 7.2 Dangling M2M association rows
--     Причина: ручной DELETE albums/categories без удаления строк link table
-- =============================================
SELECT count(*) AS dangling_m2m_rows
FROM album_category_association aca
LEFT JOIN albums   a   ON aca.album_id    = a.id
LEFT JOIN categories c ON aca.category_id = c.id
WHERE a.id IS NULL OR c.id IS NULL;

-- =============================================
-- 7.3 Completed albums with ZERO images (абракадабра)
--     Причина: AlbumWorker exception МЕЖДУ album commit и перед image INSERT
--     (Atomic Commit слой 01 должен предотвращать, но ручные операции — нет)
-- =============================================
SELECT count(*) AS completed_zero_images
FROM albums a
WHERE a.status = 'completed'
  AND 0 = (SELECT count(*) FROM images i WHERE i.album_id = a.id);
```

### Если какой-то count > 0 → quick fix:
```sql
-- Fix 7.1 Orphan images (удалить — всё равно ссылки нет)
DELETE FROM images WHERE id IN (
  SELECT i.id FROM images i LEFT JOIN albums a ON i.album_id=a.id WHERE a.id IS NULL
);

-- Fix 7.2 Dangling M2M (строки-призраки — удалить)
DELETE FROM album_category_association WHERE (album_id, category_id) IN (
  SELECT aca.album_id, aca.category_id FROM album_category_association aca
  LEFT JOIN albums a ON aca.album_id=a.id
  LEFT JOIN categories c ON aca.category_id=c.id
  WHERE a.id IS NULL OR c.id IS NULL
);

-- Fix 7.3 Completed 0 images → сбросить на error/pending, перезапустить worker
UPDATE albums
SET status = CASE WHEN id % 2 = 0 THEN 'error' ELSE 'pending' END,
    updated_at = now()
WHERE status='completed' AND 0=(SELECT count(*) FROM images i WHERE i.album_id=albums.id);
```

---

## Рецепт 8. Health-check обложек: sync ratio is_cover=true

Проверяет как много альбомов `completed` вообще не имеют ни одного изображения с `is_cover=true` (обложка не синхронизировано fix_covers).

### 8.1 SQL count healthcheck
```sql
WITH completed_albums AS (
  SELECT count(*) AS total FROM albums WHERE status='completed'
),
no_cover AS (
  SELECT count(*) AS bad
  FROM albums a
  WHERE a.status='completed'
    AND 0 = (SELECT count(*) FROM images i WHERE i.album_id = a.id AND i.is_cover = true)
)
SELECT
  ca.total AS completed_total,
  nc.bad   AS no_cover_count,
  round(nc.bad::numeric / NULLIF(ca.total,0)::numeric * 100, 2) AS no_cover_percent
FROM completed_albums ca, no_cover nc;
```

### 8.2 Интерпретация результата
| no_cover_percent | Диагноз | Действие |
|---|---|---|
| ≤ 1% | ✅ Норма | Ничего не делать |
| 1% — 25% | ⚠️ Minor issue | Запустить `scripts/fix_covers.py` (Layer01 recipe 6) |
| > 25% | 🔴 Критично | Сначала запустить `fix_covers.py`, потом проверить логи `AlbumWorker` на пропуск `process_one_album` → проверка atomic commit |

Запуск fix_covers (см. layer01 docs):
```powershell
# 0 аргументов, batch_size=200 hardcoded
.\\.venv\\Scripts\\python.exe scripts\\fix_covers.py
```

---

*Для архитектурных объяснений — [explanation.md](file:///c:/Users/Void/Desktop/yupoo-parser/docs/02-database-and-storage/explanation.md), для справочника DTO/индексов/сигнатур — [reference.md](file:///c:/Users/Void/Desktop/yupoo-parser/docs/02-database-and-storage/reference.md).*
