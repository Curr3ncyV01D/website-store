# Справочник: CLI-флаги, security.py, TelegramService и PlaywrightService

Аннотация: Полный перечень CLI-флагов и аргументов скриптов парсинга, сигнатуры всех функций и утилит `security.py` (инварианты Reseller Protection), а также публичные сигнатуры методов `TelegramService` и `PlaywrightService` с типами аргументов и возвращаемых значений.

---

## 3.1 CLI-справочник скриптов

Все скрипты расположены в директории `scripts/`. Запуск из корня проекта через интерпретатор venv:
```bash
.\\.venv\\Scripts\\python.exe scripts\\<script_name>.py [флаги]
```

---

### 3.1.1 `scripts/run_discovery.py` — Разведка категорий

Скрипт не использует `argparse`, CLI-аргументы отсутствуют.

| Флаг | Тип | Default | Описание |
|---|---|---|---|
| — | — | — | Скрипт запускается без аргументов. Поднимает Playwright, обходит дерево категорий Yupoo и сохраняет связи Category↔AlbumReference в БД. |

Код: [run_discovery.py](file:///c:/Users/Void/Desktop/yupoo-parser/scripts/run_discovery.py)

---

### 3.1.2 `scripts/run_crawler.py` — Сбор ссылок на альбомы (фильтр по брендам)

| Флаг | Тип | Default | Описание |
|---|---|---|---|
| `--limit-categories` | `int` | `None` | Для тестирования: обработать только первые N категорий (остальные пропустить). |
| `--page-size-hint` | `int` | `120` | Ожидаемое кол-во альбомов на одной странице категории. Паганация останавливается, если на странице меньше элементов (детектируется последняя страница). |

**Пример запуска:**
```bash
.\\.venv\\Scripts\\python.exe scripts\\run_crawler.py --limit-categories 5 --page-size-hint 120
```

**Фильтрация брендов:** управляется переменной окружения `CRAWL_KEYWORDS` в `.env` (список через запятую, регистр не важен, дедуп). Если `CRAWL_KEYWORDS` пуст — обрабатываются ВСЕ категории. См. [how-to.md §2](file:///c:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/how-to.md).

Код: [run_crawler.py:L23-L37](file:///c:/Users/Void/Desktop/yupoo-parser/scripts/run_crawler.py#L23-L37)

---

### 3.1.3 `scripts/run_worker.py` — Воркер заливки альбомов в Telegram CDN

| Флаг | Тип | Default | Описание |
|---|---|---|---|
| `--limit` | `int` | `None` | Обработать только первые N попыток альбомов (успех ИЛИ ошибка засчитываются в лимит). Для MVP-тестов: 5–10. |
| `--interval` | `float` | `2.5` | Пауза в секундах между циклами выборки очереди `pending → processing`. Рекомендуемый диапазон: 2–5 (выше — ниже риск 429 Telegram). |
| `--headless` | `store_true` | `True` | Запустить Playwright в headless-режиме (без видимого окна браузера). По умолчанию — активно. |
| `--headed` | `store_false` (dest=`headless`) | — | Отключить headless: запустить браузер видимым (для отладки 567 ошибок, просмотра прогрева сессии). |

**Примеры запуска:**
```bash
# MVP-тест: 10 альбомов, видимый браузер, пауза 2с
.\\.venv\\Scripts\\python.exe scripts\\run_worker.py --limit 10 --interval 2.0 --headed

# Production: headless, пауза 3с
.\\.venv\\Scripts\\python.exe scripts\\run_worker.py --interval 3.0
```

Код: [run_worker.py:L20-L46](file:///c:/Users/Void/Desktop/yupoo-parser/scripts/run_worker.py#L20-L46)

---

### 3.1.4 `scripts/fix_covers.py` — Синхронизация обложек по хэшу

Скрипт не использует `argparse`, CLI-аргументы отсутствуют. Размер батча жёстко задан в коде: `batch_size=200`.

| Флаг | Тип | Default | Описание |
|---|---|---|---|
| — | — | — | Скрипт запускается без аргументов. Проходит по всем альбомам с `cover_url is not null`, вычисляет Yupoo-хэш из URL обложки, ищет совпадение по хэшу среди изображений альбома → проставляет `target_cover_idx`. Fallback-логика: если idx=0 содержит размерную таблицу (keywords: `size chart cm us eu uk table inches`), а альбом содержит >1 фото — берётся idx=1. |

**Запуск:**
```bash
.\\.venv\\Scripts\\python.exe scripts\\fix_covers.py
```

Код: [fix_covers.py:L40](file:///c:/Users/Void/Desktop/yupoo-parser/scripts/fix_covers.py#L40) (batch_size hardcoded).

---

### 3.1.5 `scripts/fix_broken_titles.py` — Восстановление повреждённых заголовков

| Флаг | Тип | Default | Описание |
|---|---|---|---|
| `--limit` | `int` | `None` | Обработать только первые N альбомов с `broken_title=True` (для прогонки части базы). Если не указан — обрабатываются ВСЕ битые альбомы. |

**Запуск:**
```bash
# Обработать 10 битых альбомов (проверка логики)
.\\.venv\\Scripts\\python.exe scripts\\fix_broken_titles.py --limit 10

# Обработать все битые альбомы (полный прогон)
.\\.venv\\Scripts\\python.exe scripts\\fix_broken_titles.py
```

Код: [fix_broken_titles.py:L256](file:///c:/Users/Void/Desktop/yupoo-parser/scripts/fix_broken_titles.py#L256)

---

## 3.2 Спецификация `src/core/security.py`

Модуль **инвариантов Reseller Protection**: очищает заголовки альбомов от поставщика (цены, контакты, иероглифы, ссылки Weidian/Taobao) и нормализует названия брендов категорий. Все внешние DTO и шаблоны используют **только** выход этих функций.

Код: [security.py](file:///c:/Users/Void/Desktop/yupoo-parser/src/core/security.py)

---

### 3.2.1 Функция `sanitize_category_brand()`

```python
def sanitize_category_brand(category_name: Optional[str]) -> str:
```

**Назначение:** нормализация названия бренда из имени категории (удаляет технические скобки-пояснения, оставляет только безопасные символы).

**Параметры:**
| Параметр | Тип | Обяз. | Описание |
|---|---|---|---|
| `category_name` | `Optional[str]` | Нет | Сырое имя категории (например, `"Nike Shoes (Кроссовки)"`). Если `None` или пустая строка — возвращает `""`. |

**Возвращаемое значение:** `str` — очищенное имя бренда (без скобок, спецсимволов; только `A-Za-z0-9 &'-.`). Гарантируется: нет множественных пробелов, нет ведущих/хвостовых пробелов.

**Алгоритм (последовательность шагов):**
1. **Strip содержимого скобок** → `_CATEGORY_BRAND_STRIP_PATTERN` удаляет всё внутри `(...)` и `（...）` вместе со скобками.
2. **Split+filter tokens** → разбиение по пробелам, фильтрация пустых токенов.
3. **Очистка неразрешённых символов** → `_CLEAN_BRAND_PATTERN` оставляет только `[^A-Za-z0-9 &'’\-.]`.
4. **Коллапс множественных пробелов** → `_MULTISPACE_PATTERN` заменяет `\s{2,}` на одиночный пробел.

**Примеры:**
| Вход | Выход |
|---|---|
| `"Nike (Men)"` | `"Nike"` |
| `"New Balance Shoes（跑步）"` | `"New Balance Shoes"` |
| `None` | `""` |

Код: [sanitize_category_brand:L135-L145](file:///c:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L135-L145)

---

### 3.2.2 Функция `clean_album_title()`

```python
def clean_album_title(
    title: str,
    category_name: Optional[str] = None,
    album_id: Optional[int] = None,
) -> str:
```

**Назначение:** основной пайплайн очистки заголовков альбомов. Выполняет 8-шаговую очистку семействами regex, проверяет результат на «осмысленность», и при провале — запускает 6-уровневую fallback-цепочку восстановления.

**Параметры:**
| Параметр | Тип | Обяз. | Описание |
|---|---|---|---|
| `title` | `str` | Да | Сырой заголовок альбома от Yupoo (может содержать любые символы). |
| `category_name` | `Optional[str]` | Нет | Имя родительской категории — используется для извлечения бренда в fallback-цепочке. |
| `album_id` | `Optional[int]` | Нет | Первичный ключ альбома в БД — используется для `#ID` как последняя опция fallback. |

**Возвращаемое значение:** `str` — «чистый» заголовок. Гарантии:
- Содержит только `A-Za-z0-9`, пробелы и дефисы (прошёл через `_ALLOWED_CHARS_PATTERN`).
- Иероглифы, цены, ссылки, маркетплейс-теги — удалены.
- Результат всегда длиной ≥ 1 символ (пустота невозможна благодаря fallback-цепочке).

---

#### Семейства регулярных выражений (порядок применения)

Пайплайн очистки (в порядке **исполнения** внутри `clean_album_title`):

| № | Семейство переменной | Кол-во regex | Назначение | Ключевые примеры паттернов |
|---|---|---|---|---|
| 1 | `_HYPHEN_VARIANTS` | 3 нормализации | Унификация символов-дефисов: `– → -`, `— → -`, `_ → -`. | `("–", "-"), ("—", "-"), ("_", "-")` |
| 2 | `_CHINESE_CHARS_PATTERN` | 1 regex | Удаление иероглифов Unicode диапазона `\u4e00-\u9fff`. | `[\u4e00-\u9fff]` |
| 3 | `_URL_PATTERNS` | 4 regex | Удаление всех ссылок: http(s), www., домены .com/.cn/.ru и т.д., пути `*/item.html`. | `https?://\S+`, `www\.\S+`, `\b[\w\-]+\.(?:com\|cn\|ru\|...)\b\S*`, `[\w.]+/\S*item(?:\.html\|/)?\S*` |
| 4 | `_TECHNICAL_TOKENS` | 9 regex | Удаление технических токенов маркетплейсов: `weidian`, `taobao`, `1688`, `itemid=NNN`, `spm=...`, `utm_*=...`. | `\bweidian\b`, `\btaobao\b`, `\b1688\b`, `\bitemid=\d+\b`, `\butm_[A-Za-z_]+=\S+` |
| 5 | `_PRICE_PATTERNS` | 8 regex | Удаление всех цен: юани `¥` / `￥`, доллары `$`, постфикс `Y`, десятичные `.NN` цены. | `¥\s*\d+`, `$\s*\d+`, `\d+\s*¥`, `\d+[.,]\d{2,3}(?=\s\|$)`, `(?<!\w)\d{2,3}[.,]\d{2}(?!\w)` |
| 6 | `_SIZE_RANGE_PATTERN` | 1 regex | Удаление диапазонов размеров одежды: `XS-M`, `S-XXL`, `3XL-5XL` (en-dash / em-dash / минус). | `(?<![A-Za-z0-9])(XXS\|XS\|S\|M\|L\|XL\|XXL\|XXXL\|2XL\|...)\s*[-–—]\s*(...)(?![A-Za-z0-9])` |
| 7 | `_SINGLE_SIZE_PATTERN` | 1 regex | Удаление одиночных размеров одежды (после диапазонов, чтобы не словить обрезок). | `(?<![A-Za-z0-9])(XXS\|XS\|S\|M\|L\|XL\|XXL\|...)(?![A-Za-z0-9])` |
| 8 | `_ALLOWED_CHARS_PATTERN` | финальный проход | Оставляет в результате **только** `[^A-Za-z0-9 \-]` — всё остальное заменяется на пробел. | Финальный фильтр-whitelist. |
| — | `_CONTACT_PATTERNS` | 4 regex | **Отключено в коде** (закомментировано L240–241 за «ненадобностью»). Удаляло бы телефоны, WeChat/WhatsApp/Telegram контакты. | — |
| — | `_ARTIFACT_PROTECT_PATTERN` | 1 regex | **Объявлен, но неактивен** в пайплайне. Зарезервирован для будущей защиты артикулов бренда (паттерны типа `ABC123-XYZ`, `ABC-12345`). | `\b(?:[A-Za-z]{1,6}[0-9][A-Za-z0-9]{0,6}-[A-Za-z0-9]+\|...)\b` |
| — | `_DIGIT_SEQUENCE_PATTERN` | 1 regex | **Используется вне пайплайна**: в `_title_is_meaningful_enough()` (порог осмысленности SKU-цифрами) и `_extract_long_digits()` (fallback chain 1 и 3). | `\b\d{6,}\b` (6+ цифр подряд = артикул/SKU) |

После очистки запускаются пост-процессоры: `_MULTIHYPHEN_PATTERN` (коллапс `--` → `-`), `_LEADING_TRAILING_HYPHEN` (удаление дефисов с краёв), `_MULTISPACE_PATTERN` (одиночные пробелы).

Код regex семейств: [security.py:L8-L81](file:///c:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L8-L81)

---

#### Проверка на «осмысленность» (`_title_is_meaningful_enough`)

После очистки результат проверяется на минимальную осмысленность. Условие **TRUE** — возвращается очищенный заголовок как есть. Если **FALSE** — запускается fallback-цепочка.

Порог осмысленности (ИЛИ):
- Есть хотя бы один `[A-Za-z]{3,}` токен (3+ латинских буквы подряд).
- Есть SKU-подобная цифровая последовательность `\d{6,}` + либо нет бренда, либо есть хотя бы 1 буквенный токен.
- Либо ≥2 буквенных токенов суммарной длиной ≥6 символов.

Код: [_title_is_meaningful_enough:L84-L115](file:///c:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L84-L115)

---

#### Fallback-цепочка восстановления (`_finalize_fallback`)

**6 уровней** (проверяются по порядку; первый с результатом длиной ≥4 — возвращается):

| Уровень | Формат | Условие |
|---|---|---|
| 1 (highest priority) | `"{brand} {digits}"` | Есть sanitized_brand И есть 6-значная последовательность в raw/original title. |
| 2 | `"{brand} #{album_id}"` | Есть brand И передан `album_id`. |
| 3 | `"{digits}"` | Есть 6-значная SKU-последовательность. |
| 4 | `cleaned_candidate` (raw result) | Очищенный кандидат ≥4 символов. |
| 5 | `sanitized_original_title` | Иероглифы + недопустимые символы удалены из **оригинального** тайтла (ещё раз прогон). |
| 6 | `brand #{album_id}` / `brand` | Только бренд (с #ID если доступен). |
| 7 (absolute lowest) | `cleaned_candidate.strip() \|\| original_title.strip() \|\| ""` | Абсолютный保底 — возвращаем что-нибудь. |

Код: [_finalize_fallback:L148-L203](file:///c:/Users/Void/Desktop/yupoo-parser/src/core/security.py#L148-L203)

---

## 3.3 Спецификация `src/services/playwright_service.py`

Stealth-браузер на базе Playwright (Chromium) + playwright_stealth. Решает две задачи слоя Acquisition: (1) получение HTML-страниц категорий/альбомов с обходом HTTP 567, (2) скачивание байтов изображений с инжектом `Referer` (обход hotlinking-защиты Yupoo CDN).

Код: [playwright_service.py](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/playwright_service.py)

---

### 3.3.1 Модульные константы (defaults)

| Константа | Тип | Значение | Назначение |
|---|---|---|---|
| `DEFAULT_YUPOO_REFERER` | `str` | `"https://3125tiger.x.yupoo.com/"` | Значение заголовка `Referer` по умолчанию (инжектится во все page.goto и image-запросы). |
| `DEFAULT_USER_AGENT` | `str` | `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"` | Desktop Chrome 126 Windows 10 — используется как `user_agent` BrowserContext. |
| `DEFAULT_NAVIGATION_TIMEOUT_MS` | `int` | `60_000` | Таймаут навигации `page.goto` (60 секунд). |
| `DEFAULT_REQUEST_TIMEOUT_MS` | `int` | `45_000` | Таймаут обычных запросов + image-запросов через `context.request.get` (45 секунд). |
| `DEFAULT_JITTER_MIN` | `float` | `1.0` | Минимальная случайная задержка между запросами (секунды). |
| `DEFAULT_JITTER_MAX` | `float` | `3.0` | Максимальная случайная задержка между запросами (секунды). |

Код: [playwright_service.py:L57-L66](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/playwright_service.py#L57-L66)

---

### 3.3.2 Класс `PlaywrightService` — сигнатура конструктора

```python
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
```

| Параметр | Тип | Default | Источник env fallback | Описание |
|---|---|---|---|---|
| `proxy_url` | `Optional[str]` | `None` | `PROXY_URL` (L83) | URL HTTP/HTTPS/SOCKS5-прокси для браузера (`server:` формат Playwright). Если `None` — берётся из env. |
| `user_agent` | `str` | Chrome 126 Win10 | — | User-Agent, передаётся в `BrowserContext`. |
| `referer` | `str` | `3125tiger.x.yupoo.com` | — | Referer-URL, инжектится в `extra_http_headers` и при каждом image-запросе. |
| `navigation_timeout_ms` | `int` | `60_000` | — | `set_default_navigation_timeout`. |
| `request_timeout_ms` | `int` | `45_000` | — | `set_default_timeout` + `context.request.get timeout=`. |
| `headless` | `bool` | `True` | — | `chromium.launch(headless=...)`. `False` — видимый браузер (отладка). |

Код: [PlaywrightService.__init__:L74-L101](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/playwright_service.py#L74-L101)

---

### 3.3.3 Публичные методы `PlaywrightService`

| Метод | Сигнатура | Возврат | Исключения | Описание |
|---|---|---|---|---|
| `start()` | `async def start(self) -> None` | `None` | Playwright ошибки, RuntimeError | Запускает драйвер Playwright → Chromium → BrowserContext с referer/UA → прогревает сессию `page.goto(referer)` + stealth патчи. Идемпотентно: при уже запущенном браузере — no-op. |
| `stop()` | `async def stop(self) -> None` | `None` | — (ошибки игнорируются с warning) | Грациозное закрытие 4 ресурсов по порядку: `Page` → `BrowserContext` → `Browser` → `Playwright`. Все ошибки ловятся и суммируются в один warning log. |
| `get_page_content()` | `async def get_page_content(self, url: str) -> str` | `str` — HTML страницы | `PlaywrightTimeoutError`, `RuntimeError` (HTTP 567/≥400 после ретрая) | Jitter 1–3с → `context.set_extra_http_headers(Referer=...)` → `page.goto`. При **HTTP 567**: перепрогрев referer-страницы (2–4с + 1–2.5с джиттер) + один повторный retry. |
| `get_image_bytes()` | `async def get_image_bytes(self, url: str, referer: Optional[str] = None) -> bytes` | `bytes` — сырой бинарный контент изображения | `PlaywrightTimeoutError`, `RuntimeError` (response.ok is False) | Jitter 1–3с → **контекстный запрос через `context.request.get`** (не `page.goto`!) с явным инжектом заголовков: `Referer`, `Accept: image/*`, `Accept-Language`, `User-Agent`. Это обходит hotlinking Yupoo CDN. |

Дополнительно: класс поддерживает **асинхронный контекст-менеджер**:
```python
async with PlaywrightService(headless=False) as pw:
    html = await pw.get_page_content("https://.../albums/12345")
    img_bytes = await pw.get_image_bytes("https://photo.yupoo.com/.../abc.jpg")
# __aexit__ автоматически вызывает stop()
```

Код:
- start: [L103-L148](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/playwright_service.py#L103-L148)
- get_page_content: [L153-L188](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/playwright_service.py#L153-L188)
- get_image_bytes: [L190-L227](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/playwright_service.py#L190-L227)
- stop + context manager: [L229-L274](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/playwright_service.py#L229-L274)

---

## 3.4 Спецификация `src/services/telegram_service.py`

Клиент aiogram Bot API для использования Telegram канала как **бесплатного безлимитного CDN-хранилища**. Два ключевых метода: (1) заливка байтов → получение вечного `file_id`, (2) обратная загрузка байтов по `file_id` (для миграции/бэкапа). Встроенная ретраи-логика с exponential backoff и обработкой `TelegramRetryAfter` (429).

Код: [telegram_service.py](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/telegram_service.py)

---

### 3.4.1 Переменные окружения (конфигурация)

Все параметры конструктора имеют fallback из `.env`. Порядок приоритета: **явный аргумент → env → default/error**.

| Env-ключ | Маппинг в конструктор | Обяз. | Тип значения | Описание |
|---|---|---|---|---|
| `TG_TOKEN` | `bot_token` | **Да** | `str` | Bot token Telegram (получить у `@BotFather`). Если пуст → `RuntimeError`. |
| `TG_CHAT_ID` | `chat_id` | **Да** | `int \| str` | ID канала/супергруппы/лички куда заливаются фото. `int` ( `-100...` для супергрупп/каналов) или `str` (`@channel_username`). |
| `PROXY` | `proxy_url` | Нет | `str` | URL прокси для aiogram (http:// или socks5://). Маскируется в логах при наличии basic auth. |
| `PROXY_URL` | `proxy_url` | Нет | `str` | Алиас ключа `PROXY` — проверяется вторым, если `PROXY` пуст. |

Константы default-значений модуля:

| Константа | Значение |
|---|---|
| `DEFAULT_MAX_RETRIES` | `3` |
| `DEFAULT_RETRY_BACKOFF_BASE` | `2.0` (секунды → 1с, 2с, 4с backoff) |
| `DEFAULT_REQUEST_TIMEOUT` | `60` (секунд на aiogram/aiohttp запрос) |

Код env lookup: [telegram_service.py:L30-L59](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/telegram_service.py#L30-L59)

---

### 3.4.2 Класс `TelegramService` — сигнатура конструктора

```python
class TelegramService:
    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[int | str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        proxy_url: Optional[str] = None,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
```

| Параметр | Тип | Default | Fallback | Описание |
|---|---|---|---|---|
| `bot_token` | `Optional[str]` | `None` | `TG_TOKEN` env | **Обязательно** (явно или env). |
| `chat_id` | `Optional[int \| str]` | `None` | `TG_CHAT_ID` env | **Обязательно** (явно или env). Автоматически `int()` если числовой. |
| `max_retries` | `int` | `3` | — | Максимальное кол-во попыток с重试. Если передан ≤0 — сброс на `3`. |
| `proxy_url` | `Optional[str]` | `None` | `PROXY` / `PROXY_URL` env | Прокси для AiohttpSession aiogram (см. PROXY_ENV_KEYS). |
| `request_timeout` | `int` | `60` | — | ClientTimeout aiohttp (сек). Если ≤0 — сброс на `60`. |

Код: [TelegramService.__init__:L62-L112](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/telegram_service.py#L62-L112)

---

### 3.4.3 Публичные методы `TelegramService`

| Метод | Сигнатура | Возврат | Исключения | Описание |
|---|---|---|---|---|
| `is_running()` | `def is_running(self) -> bool` | `bool` | — | Возвращает `True` если `_started=True` и `_bot` экземпляр не None. |
| `start()` | `async def start(self) -> None` | `None` | — (если токен/чат_ид уже проверены) | Thread-safe async запуск сессии `AiohttpSession` + `Bot` (`DefaultBotProperties: parse_mode=None, protect_content=None`). Идемпотентно: двойной вызов no-op (double-checked locking через `asyncio.Lock`). |
| `stop()` | `async def stop(self) -> None` | `None` | — | Закрывает `bot.session.close()` → `AiohttpSession.close()` → сброс `_started=False`. Идемпотентно. |
| `upload_photo()` | `async def upload_photo(self, image_bytes: bytes \| io.BytesIO, caption: str = "") -> str` | `str` — **вечный file_id** (лучшего разрешения `msg.photo[-1].file_id`) | `ValueError` (пустые байты); после `max_retries` неудач — последнее исключение (`TelegramRetryAfter`, `TelegramNetworkError`, `TelegramServerError`, `ClientError`, `TimeoutError`) | Оборачивает байты в `BufferedInputFile(filename="photo.jpg")`, обрезает caption до **1024 chars** с троеточием, отправляет `send_photo(..., disable_notification=True)`. После успеха — `del raw_bytes/input_file + gc.collect()` (предотвращение утечек памяти при 30k+ альбомах). |
| `download_file()` | `async def download_file(self, tg_file_id: str, *, request_timeout: Optional[int] = None) -> bytes` | `bytes` — сырой контент файла из Telegram | `ValueError` (пустой file_id); после всех ретраев — последнее исключение | `bot.get_file(file_id=...)` → `bot.download(destination=io.BytesIO())` → `buf.getvalue()`. После успеха — `gc.collect()`. Переопределяет `request_timeout` для этого конкретного вызова (иначе берётся из конструктора). |

Также поддерживается **асинхронный контекст-менеджер**:
```python
async with TelegramService() as tg:
    file_id = await tg.upload_photo(image_bytes=b"...", caption="Air Jordan 1")
    restored_bytes = await tg.download_file(file_id, request_timeout=120)
```

Код:
- start/stop/lifecycle: [L119-L188](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/telegram_service.py#L119-L188)
- upload_photo + retry loop: [L190-L284](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/telegram_service.py#L190-L284)
- download_file + retry loop: [L286-L373](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/telegram_service.py#L286-L373)

---

### 3.4.4 Механика обработки ошибок и ретраев

Внутри `upload_photo` и `download_file` идентичен цикл `while attempt < max_retries`. Классы исключений и стратегия backoff:

| Класс ошибки | Условие возникновения | Стратегия ожидания |
|---|---|---|
| **`TelegramRetryAfter` (HTTP 429 Too Many Requests)** | Telegram включил rate-limit на бота/чат. В атрибуте `retry_after` указано точное кол-во секунд ожидания. | `sleep(retry_after + 1.0)` — **ожидает ровно требуемое + 1с запас**. Не тратит attempt «в никуда» (attempt инкрементирован, но sleep точный). |
| **`TelegramNetworkError` / `TelegramServerError` (HTTP 5xx / сетевые ошибки Telegram)** | Проблемы на стороне Telegram (500/502/503) или разрыв соединения. | **Exponential backoff**: `backoff = 2^(attempt-1)` → attempt#1=1с, #2=2с, #3=4с. Лог содержит подсказку: «PROXY used — check …» / «no proxy — check …». |
| **`aiohttp.ClientError`** | Ошибки TCP/TLS/прокси (разрыв соединения, 407 auth, socks error). | Exponential backoff 2^(n-1). Лог с детальной подсказкой «PROXY connection dropped…». |
| **`TimeoutError`** | Запрос > `request_timeout` секунд без ответа. | Exponential backoff 2^(n-1). Лог-подсказка про скорость proxy. |
| **Все остальные `Exception`** | Непредвиденные ошибки (баг). | **БЕЗ ретрая** — немедленный `raise` (logger.exception + proxy_hint). |

После всех `max_retries` неудач — логируется error с summary (кол-во попыток, последняя ошибка, proxy=ON/OFF, timeout), затем `raise last_error` (или `RuntimeError` если `last_error` по какой-то причине None).

Код retry-loop upload: [telegram_service.py:L210-L284](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/telegram_service.py#L210-L284)
Код retry-loop download: [telegram_service.py:L299-L373](file:///c:/Users/Void/Desktop/yupoo-parser/src/services/telegram_service.py#L299-L373)

---

*Справочник Слоя 1 завершает набор документации Acquisition & CDN. Для практических рецептов — [how-to.md](file:///c:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/how-to.md), для архитектурных объяснений — [explanation.md](file:///c:/Users/Void/Desktop/yupoo-parser/docs/01-acquisition-and-cdn/explanation.md).*
