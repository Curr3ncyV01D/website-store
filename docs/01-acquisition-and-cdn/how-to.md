# Практическое руководство: Запуск краулера, воркеров, масштабирование, фиксы

Аннотация: 7 пошаговых рецептов на каждый день эксплуатации слоя Acquisition & CDN: запуск разведки категорий, сбор альбомов с фильтрацией по брендам, массовая загрузка в Telegram CDN, масштабирование воркеров в 10+ потоков, восстановление зависших задач после аварийного выключения, хэш-синхронизация обложек fix_cover.py, восстановление повреждённых битых заголовков альбомов.

---

## Перед началом: Общие пререквизиты

Все команды в этом руководстве **обязательно** выполняются из корня проекта и используют интерпретатор **виртуального окружения `.venv\Scripts\python.exe`** (системный Python не имеет пакетов из `requirements.txt` и вызывает `ModuleNotFoundError: No module named 'dotenv'`).

```bash
# Обязательно перед всеми рецептами
cd c:\Users\Void\Desktop\yupoo-parser
```

Перед запуском проверьте переменные окружения `.env`:
- `TG_TOKEN`, `TG_CHAT_ID` — без них TelegramService откажется стартовать (RuntimeError).
- `PROXY_URL` или `PROXY` — рекомендуется для обхода блокировок Yupoo из РФ/ЕС (PlaywrightService автоматически читает).
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` — доступ к PostgreSQL.
- Опционально: `CRAWL_KEYWORDS` — фильтр брендов рецепта 2.

---

## Рецепт 1. Разведка категорий поставщика (`scripts/run_discovery.py`)

Цель: Запустить первый проход по Yupoo и собрать полную карту дерева категорий (родители → подкатегории → URL-ссылки `yupoo_path`) в таблицу `category`. Это самый первый скрипт в pipeline — без категорий нечего краулить Album-ам.

Скрипт **не имеет CLI-аргументов** (нет argparse в коде, просто 30-секундный main).

### Шаг 1. Запуск

```bash
cd c:\Users\Void\Desktop\yupoo-parser
.\.venv\Scripts\python.exe scripts\run_discovery.py
```

### Шаг 2. Что происходит во время работы
1. PlaywrightService стартует в headless режиме Chromium, патчит stealth, прогревает referer сессию.
2. `CategoriesCrawler.run()` проходит все корневые страницы категорий Yupoo, сохраняет новые записи в `category.id/name/yupoo_path/parent_id/created_at`.
3. Существующие категории (по уникальному `yupoo_path`) **Upsert**: не дублируются, обновляется `name` если изменился.

### Шаг 3. Проверка результата в DBeaver / pgAdmin

```sql
-- Количество обнаруженных категорий
SELECT COUNT(*)            AS total,
       COUNT(parent_id)    AS child_count,
       COUNT(*) FILTER (WHERE parent_id IS NULL) AS root_count
FROM category;

-- Первые 20 корневых брендов-категорий
SELECT id, name, yupoo_path, parent_id
FROM category
WHERE parent_id IS NULL
ORDER BY id ASC
LIMIT 20;
```

Ожидаемый результат: 300-500 категорий суммарно, 20-50 корневых брендов.

---

## Рецепт 2. Сбор ссылок на альбомы с фильтрацией брендов (`run_crawler.py`)

Цель: Для каждой категории (отфильтрованной по `CRAWL_KEYWORDS`) — зайти, пролистать все страницы пагинации, собрать все ссылки на альбомы в таблицу `album` со статусом `pending`. На выходе — очередь задач для Recipe 3 Worker.

### Шаг 1. Настроить фильтр брендов в `.env`

Откройте `.env` в корне и задайте ключевые слова для include-фильтра — они проверяются по `Category.name` case-insensitive `ILIKE`:

```dotenv
# Пример: краулим только 4 бренда (разделитель: пробел или запятая)
CRAWL_KEYWORDS=Nike,Adidas,New Balance,Supreme
# Если оставить ПУСТЫМ — краулер пройдёт ВСЕ категории (300+ шт)
# CRAWL_KEYWORDS=
```

Реализация фильтра: [run_crawler.py#L42-L80](file:///c:/Users/Void/Desktop/yupoo-parser/scripts/run_crawler.py#L42-L80)

### Шаг 2. Запуск в тестовом режиме (5 первых категорий)

Для того чтобы не ждать 8 часов при неправильных keywords — запустите с `--limit-categories N` и посмотрите логи:

```bash
cd c:\Users\Void\Desktop\yupoo-parser
# Обработать ТОЛЬКО первые 5 отфильтрованных категорий
.\.venv\Scripts\python.exe scripts\run_crawler.py --limit-categories 5 --page-size-hint 120
```

Доступные CLI-флаги (полная таблица — в [reference.md § 3.1](file:///c:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/reference.md)):

| Флаг | Тип | Default | Назначение |
|---|---|---|---|
| `--limit-categories` | int | `None` (все) | Для MVP-тестов: обработать только первые N категорий из отфильтрованного списка. |
| `--page-size-hint` | int | `120` | Ожидаемый размер страницы. Как только на очередной странице пагинации < page-size-hint альбомов — скрипт останавливает пагинацию (критерий последней страницы). |

### Шаг 3. Проверка наполнения очереди альбомов в БД

```sql
-- Пайплайн распределение очереди (самый важный запрос всего Acquisition слоя)
SELECT status,
       COUNT(*)                     AS albums_count,
       COUNT(*) FILTER (WHERE tg_cover_file_id IS NOT NULL) AS with_cover,
       MIN(id)                     AS min_id,
       MAX(id)                     AS max_id
FROM album
GROUP BY status
ORDER BY status;

-- Примерный результат
--   pending   : 5420 альбомов (очередь для рецепта 3 Worker)
--   processing: 2      (воркеры сейчас их заливают)
--   completed : 310    (уже залили в TG)
--   error     : 8      (упали по разным причинам)
```

### Шаг 4. Production запуск (все категории)

После проверки что CRAWL_KEYWORDS работают как ожидается — убираем лимит:
```bash
.\.venv\Scripts\python.exe scripts\run_crawler.py --page-size-hint 120
```
Длительность: от нескольких минут до получаса в зависимости от размера каталога поставщика.

---

## Рецепт 3. Массовая загрузка контента в Telegram CDN (`run_worker.py`)

Цель: Взять альбомы из очереди `status='pending'` → через Playwright скачать байты каждой картинки → через TelegramService отправить в приватный канал → сохранить `image.tg_file_id` + `album.tg_cover_file_id` → `status='completed'`.

### Шаг 1. Обязательный MVP-тест (10 альбомов, видимый браузер)

Никогда не стартуйте worker с `--limit=100000` сразу — сначала убедитесь что pipeline работает на 10-20 альбомах с видимым браузером (`--headed`) чтобы увидеть своими глазами что Playwright не получает 567:

```bash
cd c:\Users\Void\Desktop\yupoo-parser
# Тест на 10 альбомов + видимый браузер + пауза 2 сек между альбомами
.\.venv\Scripts\python.exe scripts\run_worker.py --limit 10 --interval 2.0 --headed
```

CLI-аргументы `run_worker.py` (подробнее Reference §3.1):

| Флаг | Тип | Default | Назначение |
|---|---|---|---|
| `--limit N` | int | `None` | Остановиться после N попыток (успех или ошибка засчитываются одинаково). Для тестов: 5-20. |
| `--interval S.S` | float | `2.5` | Сон между альбомами (умножается на 0.6-1.4 рандомно для jitter). Меньше 1.0 — риск IP-block от Yupoo. Рекоменд: 2-5. |
| `--headless` | flag | `True` | Запустить Playwright без GUI (production). |
| `--headed` | flag | inverse `headless` | Запустить браузер видимым (отладка 567 ошибок). |

### Шаг 2. Проверка успешности тестового прогона

Скрипт в конце печатает FINAL STATS (идеальный тест на 10 альбомов):
```
  attempts (local --limit counter) : 10
  success_albums -> status completed: 9
  error_albums   -> status error    : 1
  new_tg_images  (fresh uploads)    : 72
  skipped_existing_images (reuse)   : 3
  skipped_broken_images (tiny/404)  : 0
```

Если `error_albums >= 3 из 10` → почти всегда проблема с `PROXY_URL` (прокси мёртв, нет авторизации). Посмотрите ошибки в loguru stderr.

### Шаг 3. Production запуск worker (фоновый режим)

Когда тест 10 альбомов 10/10 success — запускайте production с Windows `start /B` (аналог Linux nohup) и пишите логи в файл:

```powershell
# PowerShell / CMD production (фоновый)
cd c:\Users\Void\Desktop\yupoo-parser
Start-Process -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "scripts\run_worker.py","--interval","3.0","--headless" `
  -RedirectStandardOutput "logs\worker_stdout.log" `
  -RedirectStandardError  "logs\worker_stderr.log" `
  -WindowStyle Hidden
```

Длительность: 10 000 альбомов × 9 фото × 3s per upload = **≈30-50 часов на 1 worker**. Для ускорения — Recipe 4 масштабирование.

### Шаг 4. Мониторинг в реальном времени

Повторяйте SQL-запрос в DBeaver каждые 10 минут:
```sql
SELECT status, COUNT(*) AS cnt
FROM album
GROUP BY status ORDER BY status;
```
Нормальный production velocity: **1 worker ≈ 250-400 альбомов / час**.

---

## Рецепт 4. Масштабирование: N воркеров параллельно (2 способа)

Postgres `SKIP LOCKED` позволяет **до 50 параллельных воркеров** без единой гонки или дубликата. Используйте один из двух способов.

### Вариант А: Локально, несколько параллельных PowerShell-окон

Самый простой для Windows 10+ — открыть **6 отдельных PowerShell** окон и запустить в каждой экземпляр worker с уникальным именем лога:

```powershell
# Терминал 1
cd c:\Users\Void\Desktop\yupoo-parser
.\.venv\Scripts\python.exe scripts\run_worker.py --interval 3.0 --headless 2>&1 | Tee-Object -FilePath logs\w1.log

# Терминал 2
.\.venv\Scripts\python.exe scripts\run_worker.py --interval 3.0 --headless 2>&1 | Tee-Object -FilePath logs\w2.log

# ... повторить для w3, w4, w5, w6
```

Velocity: **6 workers × 300 альбомов/час ≈ 1 800 альбомов в час** → 10 000 альбомов за 5.5 часов вместо 50 часов.

### Вариант Б: Docker Compose `--scale worker=N`

Если вы запускаетесь через docker-compose.yml — достаточно одной команды без редактирования compose-файла:

```bash
cd c:\Users\Void\Desktop\yupoo-parser

# Одной командой запустить 12 параллельных воркеров
docker compose up -d --build --scale worker=12

# Проверить что 12 контейнеров worker живы
docker compose ps --services | grep worker | wc -l
# ожидается 12

# Агрегированные логи со всех 12 воркеров
docker compose logs -f --tail=50 worker
```

**Правильный размер scale N**: не больше, чем `Количество pending альбомов / 500`. Если у вас в очереди 5 000 альбомов — **оптимально 8-12 workers**. При >20 начинается lock contention на индексы album.status и latency SELECT растёт.

---

## Рецепт 5. Восстановление «зависших» задач (`processing` → `pending`)

Проблема: если воркер был убит жёстко (`kill -9`, `taskkill /F`, bluescreen, power loss) **ПОСЛЕ того как PostgreSQL уже закоммитил UPDATE status='processing'**, но ДО commit status='completed' → альбом навсегда зависает в `processing`. Симптом: запрос очереди показывает processing=5 уже 2 дня, ни один воркер не берёт их.

### Шаг 1. Найти зависшие альбомы

```sql
-- Альбомы в processing уже дольше 30 минут (допустимый timeout на 1 альбом с 20 фото ≈ 5 мин)
SELECT id, title, status, updated_at,
       NOW() - updated_at                     AS stuck_duration,
       (SELECT COUNT(*) FROM image i WHERE i.album_id = a.id) AS img_count
FROM album a
WHERE status = 'processing'
  AND updated_at < NOW() - INTERVAL '30 minutes'
ORDER BY updated_at ASC;
```

Типичный сценарий: 5-20 таких строк после аварии питания.

### Шаг 2. Сбросить зависшие назад в `pending`

```sql
-- ✅ SAFE сброс (только те, что залипли >30 минут — живые воркеры не попадут)
UPDATE album
SET status      = 'pending',
    updated_at  = NOW()
WHERE status = 'processing'
  AND updated_at < NOW() - INTERVAL '30 minutes';

-- Сколько сбросили? → отобразится в сообщении "UPDATE N"
```

После этого воркеры через 2-3 секунды автоматически возьмут эти альбомы снова. Dedup-механизм (§4.1 explanation) защитит от повторной отправки уже-залитых картинок.

---

## Рецепт 6. Автоисправление размерных таблиц на обложках (`fix_cover.py`)

Проблема: многие Yupoo-поставщики на первую позицию альбома ставят **таблицу размеров** (`size chart`), а сам реальный товар — на позицию 1 (2-е фото). Потенциальные покупатели заходят на карточку и видят скриншот excel вместо кроссовок — конверсия в заказ падает в 3-5 раз.

Скрипт `fix_cover.py` **не имеет CLI-аргументов** (batch_size=200 захардкожен в L40). Алгоритм:
  1. Для каждого альбома ищет **hash совпадение** между `album.cover_url` (что показывает витрина Yupoo) и `image.yupoo_origin_url` (какая позиция в альбоме) — функция `extract_yupoo_hash()` [fix_cover.py#L19-L37](file:///c:/Users/Void/Desktop/yupoo-parser/scripts/fix_cover.py#L19-L37).
  2. Если совпадения нет **И** позиция 0 содержит `size / table / chart` в URL → авто-переключение обложки на изображение 1 (fallback stats_fallback_pos1).
  3. Если ничего не сработало — оставляем первое фото.

### Запуск

```bash
cd c:\Users\Void\Desktop\yupoo-parser
.\.venv\Scripts\python.exe scripts\fix_cover.py
```

В конце лога будут key-метрики:
```
Найдено альбомов: 5420
stats_matched_and_updated : 847   (хэш обложки совпал с img N — обновили)
stats_already_correct     : 4201  (обложка уже была правильная)
stats_fallback_pos1       : 312   (фото 0 — size chart, автопереключили в 1)
stats_no_match            : 60    (не смогли определить — оставили)
```

Рекомендованная частота запуска: **1 раз после каждого большого run_crawler.py**.

---

## Рецепт 7. Восстановление повреждённых заголовков (`fix_broken_titles.py`)

Проблема: из-за багов ранних версий краулера, смешанных кодировок win1251/utf-8, крашей Playwright при парсинге DOM — часть заголовков `album.clean_title` превращается в мусор: `глоб┼║├┤└╗ре─╠`, или содержит лишние артикулы-поставщика, постфиксы `| 3125tiger Supplier Product Catalog ...`.

Скрипт имеет один CLI-аргумент:

| Флаг | Тип | Default | Назначение |
|---|---|---|---|
| `--limit N` | int | `None` | Обработать только первые N битых альбомов из батча (MVP-проверка). |

Алгоритм работы [fix_broken_titles.py#L56-80](file:///c:/Users/Void/Desktop/yupoo-parser/scripts/fix_broken_titles.py#L56-L80):
  1. `title_looks_broken(original, clean)` детектирует битые паттерны: кириллица-псевдографика `╖╜§┼╬▀╓╫╪┴┬├─│■`, URL-маркеры (`weidian/taobao/itemid`), несуществующие store-suffixes.
  2. Если битый → через httpx **ретрайвит оригинальную страницу альбома** с правильными Referer+UA, заново парсит `<title>` из HTML.
  3. Новый title прогоняет через `clean_album_title()` security.py + сохраняет.
  4. `BATCH_SIZE=50` обновлений — каждые 50 альбомов один SQL commit (оптимизация latency).

### Шаг 1. Тест на 10 альбомов

```bash
cd c:\Users\Void\Desktop\yupoo-parser
.\.venv\Scripts\python.exe scripts\fix_broken_titles.py --limit 10
```

Посмотрите в loguru INFO на строки вида:
```
INFO Title restored: [╗╓╫ old broken title] -> [Nike Dunk Low Retro Panda DD1391-100]
```

### Шаг 2. Production полный запуск

```bash
.\.venv\Scripts\python.exe scripts\fix_broken_titles.py
```

Частота запуска: **1 раз после крупных миграций / версий краулера**, либо после импорта старых дампов из внешних источников.
