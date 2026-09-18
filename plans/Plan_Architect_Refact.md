# План реализации: Архитектурный рефакторинг и декомпозиция (Code Cleanliness & SOLID)

## Цель рефакторинга
Устранить технический долг, разгрузить «монолитные» файлы (`router.py`, `queries.py`, `base.html`), сократив их объем до **80–200 строк**, устранить дублирование логики (DRY) и разделить ответственность модулей (SOLID/KISS).

---

## Фаза 1. Декомпозиция слоя БД: `src/db/queries.py`
**Цель:** Разделить единый файл на 460 строк на модульный пакет с изолированными доменами.

### 1.1. Выделение DTO и схем (`src/db/schemas.py`)
* Создать файл `src/db/schemas.py`.
* Перенести туда все чистые `@dataclass`:
  * `AlbumCard`
  * `AlbumDetail`
  * `AlbumSearchHit`
  * `CategoryMenuRow`
  * `BreadcrumbItem`
  * `PaginatedAlbums`
* **Очистка:** Удалить неиспользуемые устаревшие DTO дерева категорий (`CategoryNode`, `RootCategoryBranch`), так как меню переведено на плоский список.

### 1.2. Превращение `queries.py` в пакет `src/db/queries/`
* Заменить одиночный файл `src/db/queries.py` на директорию `src/db/queries/` со следующей структурой:
  * `__init__.py` — реэкспорт всех публичных функций и DTO для сохранения обратной совместимости импортов по всему проекту.
  * `helpers.py` — служебные функции очистки и форматирования (`_clean_query`, `_first_letter`, `_bulk_cover_ids`, `_attach_covers_stmt`).
  * `albums.py` — операции с альбомами (`get_album_detail`, `get_latest_albums`, `get_latest_albums_paginated`, `get_category_albums_paginated`).
  * `categories.py` — операции с категориями (`get_category_by_id`, `get_category_path`, `get_all_categories_with_counts`).
  * `search.py` — поиск по триграммам и автокомплит (`search_albums`, `search_albums_suggest`).

---

## Фаза 2. Слой сервисов и рефакторинг `src/modules/web/router.py`
**Цель:** Очистить роутер от непрофильной работы с файлами, кэшем и дублированием подключений к БД.

### 2.1. Создание медиа-сервиса (`src/services/media_service.py`)
* Создать класс `MediaService`, инкапсулирующий работу с изображениями:
  * Проверка локального дискового кэша (`data/media_cache/{id}.jpg`).
  * Генерация и отдача fallback-заглушки (`no-image.png` / байтовый fallback).
  * Скачивание файла через синглтон `TelegramService`.
  * Асинхронная запись кэша на диск через `aiofiles`.
  * Формирование корректного `FileResponse` / `Response` с заголовками `Content-Disposition: inline` и `Cache-Control`.
* Обработка favicon (`/favicon.ico`) и SVG-заглушки переносится в этот же сервис (или вспомогательный модуль).

### 2.2. Очистка `router.py` от дублирования БД (DRY)
* **Удалить полностью:**
  * `_build_database_url_for_router()`
  * `_ROUTER_ENGINE`
  * `_ROUTER_SESSION_FACTORY`
  * `_router_get_session_factory()`
* Использовать стандартные механизмы: `get_db_session` и `get_session_factory` из существующего `src/db/session.py`.

### 2.3. Вынос вспомогательной логики брендов
* Вынести функции `_top_keyword_brands` и `_pick_brand_category_ids` в сервисный слой (например, `src/services/brand_service.py` или в модуль категорий), чтобы роутер оставался тонким контроллером.

### 2.4. Итог для `router.py`
* В файле остаются только чистые декораторы `@router.get(...)`, принимающие `Request` / `Depends`, вызывающие нужный сервис/запрос и отдающие `TemplateResponse` / `JSONResponse`.
* Объем файла снижается с **500 строк до ~130–170 строк**.

---

## Фаза 3. Декомпозиция фронтенда: `templates/base.html`
**Цель:** Сократить главный шаблон с 660 строк до ~70 строк, вынеся тяжелый JavaScript и разметку компонентов.

### 3.1. Вынос JavaScript в `static/js/`
* **`static/js/search.js`**:
  * Зарегистрировать Alpine-компонент через `Alpine.data('headerSearch', () => ({ ... }))`.
  * Перенести туда всю логику поиска, которая сейчас громоздко зашита прямо в HTML-атрибут `x-data='...'` тега `<header>`:
    * Фокус, мобильное развертывание, debounce, AbortController, клавиатурная навигация, сброс.
* **`static/js/menu.js`**:
  * Вынести всю логику шторки меню из инлайн-скрипта внизу `base.html`:
    * `openMenu()`, `closeMenu()`, `loadMenu()`, сортировка языков (EN -> RU -> Цифры), клиентская фильтрация `filterMenu()`.
* **Подключение:** В `base.html` скрипты подключаются внешними тегами:
  ```html
  <script defer src="/static/js/search.js"></script>
  <script defer src="/static/js/menu.js"></script>
  ```

### 3.2. Вынос компонентов Jinja2 в `templates/components/`
* **`templates/components/header.html`**:
  * Содержит чистую разметку шапки: кнопку меню, логотип `semsneak`, десктопный и мобильный блоки поиска.
* **`templates/components/menu_drawer.html`**:
  * Содержит разметку выдвижной панели `#menu-panel`, инпут поиска бренда, спиннер и контейнер списка.
* **`templates/components/footer.html`**:
  * Содержит разметку подвала и юридический дисклеймер (ст. 437 ГК РФ, права на товарные знаки).

### 3.3. Итог для `templates/base.html`
Шаблон превращается в легкий читаемый каркас:
```html
<!doctype html>
<html lang="ru">
<head>
  {% include "components/head.html" %}
</head>
<body class="bg-bg text-ink font-sans antialiased min-h-screen">
  {% include "components/header.html" %}
  {% include "components/menu_drawer.html" %}

  <main class="max-w-[1400px] mx-auto px-4 sm:px-6 pt-2 md:pt-6 pb-6 md:pb-10">
    {% block content %}{% endblock %}
  </main>

  {% include "components/footer.html" %}
  {% block extra_scripts %}{% endblock %}
</body>
</html>
```
Объем файла снижается с **660 строк до ~60–80 строк**.

---

## Фаза 4. Верификация и регрессионное тестирование
После выполнения каждого шага проводится проверка:
1. **Синтаксис и импорты:** запуск проверки `python -m py_compile` для всех затронутых Python-файлов.
2. **Маршруты:** проверка статус-кодов `200 OK` для:
   * Главной страницы `/`
   * Категории `/category/{id}`
   * Товара `/album/{id}`
   * Поиска `/search?q=...`
   * Подсказок `/api/search/suggest?q=...`
   * Меню `/api/menu.json`
   * Изображений `/media/image/{id}`