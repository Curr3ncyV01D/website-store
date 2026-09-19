# План: Документация Слоя 03 — Web & Frontend (Diátaxis 3 файла)

- **Контекст**: Продолжаем фреймворк Diátaxis после COMPLETED слоёв 01 (Acquisition & CDN) и 02 (Database & Storage). Качество — то же: 0 fabrication policy, все константы/URL/имена функций VERBATIM из кода, Mermaid вместо ASCII для ERD/flow, только для структур папок — ASCII tree.
- **План утверждён пользователем после NotifyUser gate — перед записью MD-файлов**.

---

## § 0. Источники исследования (Research — все VERBATIM пути)

| Источник | Строки | Что извлечено |
|----------|--------|---------------|
| `src/main.py` | 1–181 | FastAPI `create_app`, lifespan startup/shutdown (service registry + dispose_engine + TG singleton), `_mount_static("/static")`, mount web_router, `/health` endpoint, path constants `STATIC_DIR/TEMPLATES_DIR/MEDIA_CACHE_DIR` absolute |
| `src/modules/web/router.py` | 1–449 | APIRouter `web` tags; **14 HTTP routes** VERBATIM URL/HTTP methods/Depends; `_INFINITE_SCROLL_PER_PAGE=36`, `PLACEHOLDER_FILENAME="no-image.png"`; Reseller Protection invariant album_page L302–L303 comment; Telegram/Instagram order URL builder + TELEGRAM_ORDER_MESSAGE format string |
| `src/core/config.py` | 1–95 | Settings BaseSettings (Pydantic BaseModel NOT used — BaseSettings), env_file `.env`, Settings defaults MANAGER_USERNAME="ManagerSem", INSTAGRAM_USERNAME="semsneak", TELEGRAM_ORDER_MESSAGE default, REVIEWS_CHANNEL_URL="" empty; `get_recommended_brands()` helper RECOMMENDED_BRANDS CSV UPPER |
| `templates/base.html` | 1–34 | **Jinja2 inheritance root**: 2 blocks `{% block extra_head %}{% endblock %}` inside `<head>` (AFTER include components/head.html! — CRITICAL Protocol from Phase4 PhotoSwipe bugfix), `{% block content %}` in `<main>`, `{% block extra_scripts %}` before `</body>`; 3 Alpine CustomEvents window protocol `@search-open.window / @search-close.window / @resize.window`; `searchLock()` Alpine data on `<body>`; `overflow-hidden: searchLocked` scroll lock class; 4 script tags order critical (search/menu defer first, then htmx sync, then alpine defer, then extra_scripts) |
| `templates/components/head.html` | 1–80 | Tailwind CDN config inline (no build): theme.extend.colors `bg/surface/line/muted/ink` hex values, `fontFamily sans=Inter/mono=JetBrains Mono`, boxShadow card/panel; CSS utility classes: h-scroll, scrollbar-hide, x-cloak, htmx-indicator, lazy-fade opacity transition, htmx-fade-in keyframes; DOMContentLoaded + htmx:afterSwap listeners для lazy-fade markLoaded |
| `templates/components/header.html` | 1–356 | Alpine `x-data='headerSearch(initial_query)'` (factory from search.js), mobile/desktop dual search UI, dropdown shadow: `shadow-panel`, grid cols header, logo `semsneak` font-black 40px, @click.outside close desktop; search-suggest dropdown rendering Alpine `x-for r in results` r.id/r.title/r.image_id/r.url |
| `templates/components/menu_drawer.html` | 1–63 | id constants for vanilla JS: `#menu-overlay / #menu-panel / #menu-open / #menu-close / #menu-loading / #menu-content / #menu-empty / #menu-notfound / #menu-notfound-text / #menu-stats / #menu-search / #menu-search-clear`. Sidebar drawer width: `w-full max-w-[540px] sm:max-w-[680px] md:max-w-[1000px]` |
| `templates/components/album_grid_chunk.html` | 1–66 | HTMX partial fragment (NO base extends). Shared include by index/category. Card HTML classes: `group album-card htmx-fade-in`, line-clamp-2 clean_title, shadow-card hover; **hx-sentinel protocol**: `hx-get={{next_url}} hx-trigger=revealed hx-swap=outerHTML show:none scroll:none hx-target=closest div.hx-sentinel-wrap hx-indicator=.htmx-sentinel-indicator-{page}`; skeleton 6-card placeholder include |
| `templates/components/skeleton_card.html` — асинхронно чтение не требовалось (известно — include) |
| `templates/components/footer.html` — footer, id `#y` year dynamic (menu.js L2–L3 document.getElementById('y')) |
| `templates/index.html` | 1–56 | `{% extends "base.html" %}` + block content only. Recommended brands carousel pill: `snap-x`, 2.5 visible scroll effect `grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 md:gap-5 sm:gap-6`; hero card semsneak col-span-2 md:col-span-4 md:col-start-2 min-h-[160px] md:min-h-[200px]; latest_albums section with first page HTMX sentinel inject |
| `templates/category.html` | 1–40 | extends base. Breadcrumbs nav, pluralization `{{ total }} товар{% ... %}` russian case; grid classes same as index; next_url string concat with `per_page=36` constant value |
| `templates/album.html` | 1–325 | extends base. **3 critical PhotoSwipe v5 patterns**: (a) `{% block extra_head %}` → inline styles photoswipe.css + `updatePswpAttributes()` IIFE declaration (DOMContentLoaded + htmx:afterSwap syncAll). CRITICAL Protocol Phase4 fix: этот код ДО `<body>` чтобы img onload typeof guard не ReferenceError. (b) Gallery grid: `grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-1.5 md:gap-2 md:gap-3`. (c) `{% block extra_scripts %}`: ESM PhotoSwipeLightbox init options: padding 20/20/20/20, bgOpacity=0.95, showHideAnimationType='zoom'. Also: Telegram Order BottomSheet mobile Bottom + desktop center Modal; `x-effect _syncScroll` Re-entrancy guard `_weLocked` to coexist с body.searchLock already locked. Reseller Protection: ONLY clean_title/album_id/images ids — NO original_title/weidian_url in context at all |
| `templates/search.html` | 1–44 | extends base. Search results same grid classes; Russian pluralization count товаров; typo hint for 0 results "Nkie найдёт Nike" |
| `templates/about.html` | 1–170 | extends base. 4 sections hero/approach/3-steps process/reviews/3 contact cards. Settings context: manager_username, telegram_manager_url, instagram_*, reviews_channel_url. No secrets in output |
| `static/js/search.js` | 1–133 | Alpine data factories registration IIFE pattern, idempotent (if Alpine.data exists → register now else on `alpine:init`): (1) `searchLock()` — search open scroll lock savedScrollY protocol, mobile < 768 px only. (2) `headerSearch(initialQ)` — 22-публичный метод/свойство объект: open, mobileOpen, q, results, loading, idx, _abort; closeAll/openDesktop/openMobile/closeMobile(onInput + debounce300)/_doSearch fetch('/api/search/suggest?q=..&limit=8') AbortController; goResult() idx navigate/submitFull redirect /search?q=; allUrl(). Window CustomEvents: `document.dispatchEvent(new CustomEvent('search-open'/'search-close'))`. Critical: `/api/search/suggest` limit=8 VERBATIM constant |
| `static/js/menu.js` | 1–201 | Vanilla JS (no Alpine — intentional for memory): DOMContentLoaded init. openMenu → remove hidden + overflow-hidden + rAF + opacity0→1 + -translate-x-full removal. closeMenu → rAF reverse → setTimeout 180ms cleanup. fetch('/api/menu.json') lazy first open. groupByLetter function: score 1=Eng A-Z, 2=Rus А-Я, 3=# localeCompare sort. `data-letter-row`/`data-brand-name` client-side filter. Grid brands inside menu: `grid grid-cols-2 sm:grid-cols-3 gap-1.5 ml-9`. Footer stats N брендов, notfound state. filterMenu query substring match name includes() |
| `static/js/photoswipe-lightbox.esm.js`, `static/js/photoswipe.esm.js` — self-hosted bundles (факт для reference: self-hosting вместо unpkg CDN PhotoSwipe из-за sanctions/Russia блокировки) |
| `static/css/photoswipe.css` — тоже self-hosted |
| `static/images/no-image.png` — placeholder fallback if cover_image_id is None or 404 TG |

---

## § 1. Цель документации / Scope 3 Diátaxis файлов

| Файл | Квадрант Diátaxis | Объём строк ~ | Кол-во таблиц | Mermaid диаграммы |
|------|------------------|---------------|---------------|-------------------|
| `docs/03-web-and-frontend/explanation.md` | **Объяснение (Why/How it works)** | ~ 240 | 0 | 3 диаграммы Mermaid: (1) erDiagram Request Lifecycle endpoint → Depends + session/media/TG services, (2) flowchart TD Jinja2 Decomposition `extends base.html → include components/` блок-схема с 2 critical rules (block scope — НЕ внутри include, defer order search.js→htmx→alpine), (3) flowchart LR PhotoSwipe v5 integration phases init/update/click с guard typeof window.updatePswpAttributes |
| `docs/03-web-and-frontend/how-to.md` | **How-To (Recipes, пошагово)** | ~ 360 | 0 | Mermaid flowchart для 1 рецепта (Infinite Scroll chain scroll → htmx revealed → partial → swap sentinel outerHTML), ASCII tree только для templates/components структуры директорий (1 раз, разрешено) |
| `docs/03-web-and-frontend/reference.md` | **Справочник (What is, tables)** | ~ 360 | 9 таблиц | 0 Mermaid (чистый справочник) |

### Acceptance Criteria для слоя 03 (совпадает с слоями 01/02):
1. **0 Fabrication Policy**: все URL routes, env defaults, screen breakpoints, Alpine factory names, PhotoSwipe init options → VERBATIM grep match source.
2. **Mermaid вместо ASCII**: ERD, flow diagrams, архитектурные схемы — только Mermaid. ASCII tree — ТОЛЬКО для структуры папок/файлов (1 раз how-to).
3. **≥ 35 file:/// кросс-ссылок** по 3 файлам (ссылки на реальные диапазоны строк Lx-Ly исходников).
4. **Reseller Protection Invariant повторно задокументирован** в explanation+reference: `original_title` и `weidian_url` — НИКОГДА не попадают в Jinja context/HTTP JSON/DTO. Комментарий router.py L302-L303 VERBATIM цитировать.
5. **2 Critical Protocol фикса Phase4**: (a) Jinja2 `{% block extra_head %} / {% block content %} / {% block extra_scripts %}` ОБЯЗАТЕЛЬНО объявлены в **корне** `base.html` (НЕ внутри `{% include %}` — block scope bugfix), (b) `window.updatePswpAttributes()` ОБЯЗАТЕЛЬНО объявлена в `<head>` блок extra_head ДО `<body>` — чтобы img onload guard срабатывал даже для HTTP-cache моментальных onload.

---

## § 2. Содержание explanation.md (4 раздела, Why-architecture)

> Target: Объяснить архитектурные решения — почему именно FastAPI lifespan+ServiceRegistry, почему Jinja block scope именно так, почему Alpine 3.14 + HTMX 1.9.10 гибрид, почему PhotoSwipe v5 с self-host ESM.

### 2.1 FastAPI Lifespan + Service Registry (Anti-singleton дублирования)
- Проблема устаревшего pattern `@router.on_event('startup')` — singleton engine/TG создаются дважды.
- Решение: `@asynccontextmanager async def lifespan(app: FastAPI)` → `app.state.services = ServiceRegistry(tg: Optional[TelegramService], media: MediaService)` frozen dataclass VERBATIM.
- Startup flow Mermaid:
  ```
  lifespan start → ensure_dirs() → templates=Jinja2Templates(settings globals) → MediaService.ensure_dirs()+ensure_placeholder → TG TelegramService.start() fallback None if fail → app.state.services registry → yield → (shutdown) TG.stop() → dispose_engine() → delattr services
  ```
- Код-ссылки: [main.py:L31-L42 (ServiceRegistry)], [main.py:L59-L133 (lifespan)], [router.py:L58-L76 (_tpl + _media_svc Depends fallback chain)]

### 2.2 Jinja2 Decomposition Protocol (Phase4 block scope bugfix кодифицирован)
- Mermaid flowchart TD: `album.html {% extends "base.html" %}` → `base.html` HEAD → includes `components/head.html` (NO blocks inside) → затем `{% block extra_head %}` (ПЕРЕОПРЕДЕЛЯЕТСЯ ДЕТЁМ, работает потому что в корне base а не в include!) → `<body>` → includes header.html/menu_drawer.html → `<main>` → `{% block content %}` → includes footer.html → scripts defer search.js/menu.js → sync htmx → defer alpine 3.14.3 → `{% block extra_scripts %}` album.html PhotoSwipe init ESM.
- 2 hard rules CRITICAL Protocol (from PhotoSwipe bug + Alpine defer bug):
  1. `{% block %}` для переопределения → ТОЛЬКО в `base.html` root (не в included файлах). Block scope внутри include — игнорируется extends. См. [project memory lessons learned: Jinja Block Scope].
  2. Script execution order — VERBATIM [base.html:L27-L32](file:///C:/Users/Void/Desktop/yupoo-parser/templates/base.html#L27-L32): (1) `search.js defer` (Alpine factories first!), (2) `menu.js defer`, (3) `htmx.org@1.9.10 SYNC` (no defer — htmx должен обработать hx-sentinel до Alpine scan), (4) `alpinejs@3.14.3 defer`, (5) `extra_scripts block`. Если перепутать порядок → factories не зарегистрированы → Alpine ExpressionError, htmx sentinel нет swap.

### 2.3 Alpine 3.14 + HTMX 1.9.10 Hybrid (разделение ответственности)
- Почему оба: Alpine = stateful интерактив (search dropdown, scroll lock, modals, bottom sheets). HTMX = stateless infinite scroll (TCO — не нужно писать JS fetch pagination → сервер рендерит тот же album_grid_chunk.html partial → outerHTML swap sentinel).
- 2 Window CustomEvents Protocol search-lock ↔ header-search ↔ body overflow-hidden coexist: `@search-open.window / @search-close.window` + `@resize.window` (recompute mobile width). Scroll lock searchLock резервирует `document.body.dataset.savedScrollY`. Order Modal `_syncScroll()` имеет guard `_weLocked`, чтобы НЕ снимать overflow-hidden который уже поставил searchLock (взаимодействие 2 независимых Alpine data).
- Код-ссылки: [base.html:L8-L14 body attrs], [search.js:L3-L27 searchLock factory], [search.js:L29-L123 headerSearch factory], [album.html:L69-L105 _syncScroll guard _weLocked]

### 2.4 PhotoSwipe v5: Self-hosted ESM + Critical updatePswpAttributes (Phase4 Fix Protocol)
- Почему self-hosted (no unpkg CDN): санкции/Russia блокировка внешних ресурсов → стабильность важнее. Файлы self-host: [photoswipe-lightbox.esm.js], [photoswipe.esm.js], [photoswipe.css].
- Mermaid LR flow: User click a.pswp-link → default prevent (capturing listener) → PhotoSwipeLightbox reads data-pswpWidth/data-pswpHeight → zoom open. Где атрибуты width/height? `updatePswpAttributes()` читает `img.naturalWidth/naturalHeight` ПОСЛЕ load события img (до этого 1000×1000 placeholder срабатывал с aspect искажением!). **Critical Protocol Phase4**: updatePswpAttributes ОБЯЗАТЕЛЬНО в extra_head ДО body (иначе onload стреляет раньше объявления → ReferenceError). Guard typeof: `onload="(typeof window.updatePswpAttributes === 'function') && window.updatePswpAttributes(this)"` на every img [album.html:L149].
- Init options VERBATIM: `padding {top:20,bottom:20,left:20,right:20}, bgOpacity=0.95, showHideAnimationType='zoom'` [album.html:L312-L320].
- Код-ссылки: [album.html:L29-L65 updatePswpAttributes IIFE extra_head], [album.html:L298-L324 PhotoSwipeLightbox init extra_scripts]

---

## § 3. Содержание how-to.md (8+ рецептов пошагово, Windows PowerShell + venv)

### 3.1 Рецепт 1: Локальный запуск FastAPI web dev сервера (без Docker)
- Команды (venv!): `cd /d c:\Users\Void\Desktop\yupoo-parser ; .\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --port 8765`
- Проверка открыть: http://localhost:8765/, http://localhost:8765/health
- Ожидаемый результат: services.telegram_available true если .env имеет TG_TOKEN

### 3.2 Рецепт 2: Добавить новый роут + шаблон (пример: /brands топ N)
- Шаги: (1) Добавить `@router.get("/brands", response_class=HTMLResponse, tags=["pages"])` в src/modules/web/router.py → Depends session/tpl, (2) Создать templates/brands.html extends "base.html", (3) Переопределить {% block title %} и {% block content %}, (4) Не забыть Reseller Protection — передавать ТОЛЬКО clean_title, (5) Перезапустить uvicorn --reload.

### 3.3 Рецепт 3: Отладка Alpine factories (если ExpressionError: searchLock/headerSearch не определены)
- Воспроизведение: открыть DevTools Console → увидеть "Alpine Expression Error: searchLock is not defined".
- 3 гипотезы по порядку как в Phase4 scientific debug: (H1) search.js не загрузился → Network tab 200 OK?, (H2) script order в base.html — search.js ДОЛЖЕН стоять ПЕРЕД alpinejs defer AND htmx должен быть между ними → проверить [base.html:L27-L30], (H3) Alpine.data вызывался до alpine:init → idempotent IIFE pattern guard в search.js:L126-L132 (если window.Alpine → регистрируй сразу, иначе жди alpine:init listener).

### 3.4 Рецепт 4: Кастомизировать сетку карточек каталога (grid-cols-2 mobile / 6 xl)
- Классы VERBATIM для замены одновременно в 5 местах (иначе страницы отличаются!): (1) index.html:L22 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6, (2) category.html:L35 то же самое, (3) search.html:L25 то же, (4) album_grid_chunk.html:L50 skeleton grid cols то же, (5) album.html grid gallery отдельно grid-cols-3..8.

### 3.5 Рецепт 5: Кастомизация обложек PhotoSwipe атрибутов — если зум кривой aspect
- Воспроизведение: клик по картинке → оверлей отображается с искажённым aspect ratio.
- Проверки: (1) DevTools find a.pswp-link → проверить наличие data-pswpWidth/data-pswpHeight атрибутов после load img, (2) Проверить typeof window.updatePswpAttributes в консоли → function, не undefined. Если undefined: проверить Critical Protocol extra_head.
- Фикса из Phase4: `updatePswpAttributes` должна быть вызвана сразу после загрузки, syncAll для всех img.complete при DOMContentLoaded и htmx:afterSwap.

### 3.6 Рецепт 6: HTMX Infinite Scroll отладка — если перестали подгружаться страницы 2+
- 4 диагностики по порядку: (1) Прокрутить вниз → в Network tab XHR фильтровать /partial/albums?page=2 → HTTP 200?, (2) Response Content-Type text/html?, (3) В ответе должен быть div class="hx-sentinel-wrap ..." следующей страницы (hx-get page=3 next URL), (4) CSS `.htmx-request .htmx-indicator { opacity:1 display:grid }` — видны ли skeleton-карточки во время ожидания? Flow diagram Mermaid: `Scroll down → Sentinel enters viewport → htmx trigger revealed → GET /partial/albums?page=N+1 → Response 200 HTML (album_grid_chunk) → hx-swap outerHTML on closest .hx-sentinel-wrap → Новый sentinel для страницы N+2 → Repeat until has_next=False → Показать "Вы просмотрели все товары"`.

### 3.7 Рецепт 7: Reseller Protection аудит — убедиться что нет утечек original_title/weidian_url
- PowerShell Grep commands: `cd c:\Users\Void\Desktop\yupoo-parser ; Select-String -Path templates\*.html,templates\components\*.html -Pattern 'original_title|weidian_url' -List ; Select-String -Path src\modules\web\router.py -Pattern 'original_title|weidian_url' | Select-String -NotMatch 'Reseller Protection|NEVER pass|comment'`. Ожидание: 0 совпадений в templates, только 1 комментарий-запрет в router.py:L302-303.

### 3.8 Рецепт 8: Self-hosting внешних библиотек (Alpine, HTMX, Tailwind, Inter/JetBrains) — обход блокировок
- Проблема: fonts.googleapis.com, unpkg, cdn.tailwindcss.com могут блокироваться. Шаги: (1) Скачать Alpine `alpinejs@3.14.3/dist/cdn.min.js` → static/js/alpine.min.js, (2) Скачать htmx 1.9.10 → static/js/htmx.min.js, (3) Tailwind Standalone CLI → static/js/tailwindcss.js, (4) Google Fonts Inter & JetBrains Mono локально → static/fonts/, (5) Заменить в components/head.html все CDN ссылки на /static/ эквиваленты.

---

## § 4. Содержание reference.md (9 справочных таблиц, What/VERBATIM)

### §4.1 Карта HTTP Routes (web_router + /health) — 14 endpoints
| Method | Path | Tags | Роутер функция | Query/Path Params | Depends | Response Class | Строка в router/main.py |
|--------|------|------|---------------|-------------------|---------|----------------|-------------------------|
| GET | `/health` | system | health | — | Request (app.state.services) | dict JSON | main.py:L163-L176 |
| GET | `/favicon.ico` | static | favicon | — | MediaService Depends(_media_svc) | FileResponse | router.py:L81-L83 |
| GET | `/api/menu.json` | api,menu | api_menu_json | — | AsyncSession Depends(get_db_session) | JSONResponse list[{id,name,album_count,first_letter,url}] | router.py:L86-L99 |
| GET | `/` | pages | homepage | — | session, tpl | HTMLResponse index.html | router.py:L102-L146 |
| GET | `/about` | pages | about_page | — | tpl, settings globals | HTMLResponse about.html | router.py:L149-L170 |
| GET | `/partial/albums` | partial | partial_albums_grid | page:int [1,1e5], category_id Optional int | session, tpl | HTMLResponse album_grid_chunk (Cache-Control: private no-store) | router.py:L173-L223 |
| GET | `/category/{category_id}` | pages | category_page | category_id int ≥1, page:int 1–10000 | session, tpl | HTMLResponse category.html | router.py:L226-L277 |
| GET | `/album/{album_id}` | pages | album_page | album_id int ≥1 | session factory manual | HTMLResponse album.html | router.py:L280-L353 |
| GET | `/search` | search | search_page | q str ≤200, limit int 1-200, threshold 0-1 | session, tpl | 302 Redirect / если пусто; HTMLResponse search.html иначе | router.py:L356-L385 |
| GET | `/media/image/{image_id}` | media | get_media_image | image_id int ≥1 | session, media, tg_service from state.services | Response streaming (TG file_id BytesIO → placeholder fallback) | router.py:L388-L398 |
| GET | `/api/search/suggest` | api,search | api_search_suggest | q str ≤200 (if <3 → []), limit 1-50, threshold 0-1 | session | JSONResponse list[{id,title,image_id,url}] | router.py:L401-L449 |
| **Итого маршрутов** | — | — | — | — | — | — | **11 в web_router + /health = 12** |
| Static mount | `/static/*` | — | _mount_static() | subpath static/ → STATIC_DIR resolve | — | StaticFiles | main.py:L136-L145 |
| Jinja globals | — | — | _templates() | settings | — | Template env globals | main.py:L45-L48 |

### §4.2 Jinja2 Blocks Inventory (только в корне base.html! — Critical Protocol Scope)
| Block Name | Расположение в base.html | Тип контента | Переопределяется в | Назначение |
|------------|---------------------------|---------------|-------------------|------------|
| `{% block title %}` | head.html <title> L3 (в head include — НО титульник всегда override) | Text | index/category/album/search/about | `<title>` страницы |
| **`{% block extra_head %}`** | **base.html:L5 AFTER include components/head.html**! CRITICAL | meta tags, link CSS, `<script>` declarations ДО `<body>` | **ТОЛЬКО album.html** — PhotoSwipe CSS + updatePswpAttributes IIFE (для onload guard) | OG meta для Telegram share, custom per-page styles. CRITICAL: если блок будет внутри include → переопределение НЕ работает (Phase4 bug). |
| `{% block content %}` | base.html:L22 inside `<main>` | HTML per page body | ВСЕ 6 страниц: index/category/album/search/about | Основной контент |
| **`{% block extra_scripts %}`** | **base.html:L32 BEFORE `</body>`** AFTER 4 core scripts | `<script>` tags end of body | ТОЛЬКО album.html — PhotoSwipeLightbox ESM module init | Page-specific JS, запускается ПОСЛЕ defer search/menu + sync htmx + defer Alpine (Critical Protocol order!) |

### §4.3 Alpine.js Stores & Factories (static/js/search.js)
| Factory Name | Сигнатура `x-data='...'` | Используется в | Ключевые свойства/методы | Строка search.js |
|--------------|--------------------------|----------------|--------------------------|------------------|
| searchLock | `x-data="searchLock()"` | base.html `<body>` global | `searchLocked: bool`, `_searchOpen: bool`, `_isMobile() <768px`, `_updateLock()` overflow-hidden body dataset.savedScrollY, window.scrollTo 0 savedY | search.js:L3-L27 |
| headerSearch | `x-data='headerSearch({{initial_query|tojson}})'` | header.html `<header>` sticky | `open/mobileOpen/q/results/loading/idx/_abort`, methods: `emitGlobal(ev, detail)` CustomEvent, closeAll, openDesktop/openMobile/closeMobile, onInput `debounce.300ms`, _doSearch fetch /api/search/suggest limit=8 AbortController, goResult() idx→url, submitFull redirect /search?q=, allUrl /search?q= | search.js:L29-L123 |
| Inline anonymous album order scroll-lock | `x-data='{ orderModalOpen:false, _savedY:0, _weLocked:false, _syncScroll() }'` | album.html `<div>` top of content | Coexists with body.searchLock: проверяет classList.contains("overflow-hidden") уже присутствует — _weLocked=false не трогай при закрытии | album.html:L69-L105 inline |

### §4.4 PhotoSwipe v5 Integration Reference (self-hosted)
| Entity | Значение VERBATIM | Расположение |
|--------|-------------------|--------------|
| Self-hosted file ESM Lightbox | `/static/js/photoswipe-lightbox.esm.js` — 1 файл | import in extra_scripts album.html:L310 |
| Self-hosted file ESM Core | `/static/js/photoswipe.esm.js` | album.html:L315 pswpModule dynamic import |
| Self-hosted CSS | `/static/css/photoswipe.css` | album.html:L13 extra_head link rel=stylesheet |
| gallery selector | `"#album-gallery"` | album.html:L313 |
| children click selector | `"a.pswp-link"` | album.html:L314 |
| Data attributes on `<a>` anchor | `data-pswp-src="/media/image/{id}"`, `data-pswp-width/height` динамически updatePswpAttributes, initially 1000×1000 placeholder | album.html:L139-L143 |
| Lightbox options (3 only) | `padding { top:20, bottom:20, left:20, right:20 }`, `bgOpacity=0.95`, `showHideAnimationType='zoom'` | album.html:L317-L319 |
| Global variable debug | `window.__ps_lightbox = lightbox;` (для DevTools console) | album.html:L323 |

### §4.5 Tailwind CDN Design Tokens (components/head.html inline config)
| Token Type | Имя токена | Значение HEX/CSS |
|------------|-----------|------------------|
| Colors.theme.extend | bg | `#fafafa` |
| Colors | surface | `#ffffff` |
| Colors | line | `#eceff3` |
| Colors | muted | `#71717a` |
| Colors | ink | `#09090b` |
| Font Family | sans | `['Inter', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, '"Segoe UI"', Roboto, '"Helvetica Neue"', Arial, sans-serif]` |
| Font Family | mono | `['"JetBrains Mono"', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace]` |
| boxShadow | card | `0 10px 30px -10px rgba(0, 0, 0, 0.15), 0 4px 12px -6px rgba(0, 0, 0, 0.08)` |
| boxShadow | panel | `0 20px 60px -15px rgba(0, 0, 0, 0.18), 0 8px 20px -10px rgba(0, 0, 0, 0.10)` |
| Grid Responsive каталог | mobile sm md lg xl | `grid-cols-2 → sm:grid-cols-3 → md:grid-cols-4 → lg:grid-cols-5 → xl:grid-cols-6` (index/category/search/skeleton) |
| Grid Responsive gallery album | mobile sm md lg | `grid-cols-3 → sm:grid-cols-4 → md:grid-cols-6 → lg:grid-cols-8` album.html |

### §4.6 Settings .env Web Frontend defaults (config.py VERBATIM)
| Env Key | Default Value | Purpose |
|---------|---------------|---------|
| `MANAGER_USERNAME` | `ManagerSem` | Telegram username менеджера для order URL `https://t.me/{name}?text=...` |
| `TELEGRAM_ORDER_MESSAGE` | `'Здравствуйте! Хочу заказать этот товар: "{title}". Ссылка: {url}'` | Template для префилла сообщения при клике «Заказать в Telegram». Форматирует `detail.clean_title` + `current_url` |
| `INSTAGRAM_USERNAME` | `semsneak` | Instagram профиль для Direct `https://ig.me/m/{name}` |
| `REVIEWS_CHANNEL_URL` | `""` (empty string → скрывает кнопку/карточку отзывов) | URL публичного Telegram-канала с отзывами |
| `RECOMMENDED_BRANDS` | CSV empty (UPPERCASE list) | Hero carousel главной. Пример env: `RECOMMENDED_BRANDS=NIKE,ADIDAS,JORDAN,ARCTERYX,BALENCIAGA,STONE ISLAND` |

### §4.7 HTMX Endpoint Reference (partial fragments)
| Endpoint | htmx attributes sentinel | Swap Strategy | Fragment Template | Cache-Control |
|----------|--------------------------|----------------|-------------------|---------------|
| GET `/partial/albums?page=N&category_id=&per_page=36` | `hx-get="..." hx-trigger="revealed" hx-swap="outerHTML show:none scroll:none" hx-target="closest div.hx-sentinel-wrap" hx-indicator=".htmx-sentinel-indicator-{page}"` | outerHTML самого sentinel wrap (удаляет текущий div + вставляет ответ содержащий новый sentinel для next page) | `components/album_grid_chunk.html` — shared include | `private, no-store, max-age=0` router.py:L220 |

### §4.8 Vanilla JS DOM Element IDs (menu.js L1-L201) — если переименовать, сломается меню
| `document.getElementById(...)` string | Расположение HTML | Назначение |
|---------------------------------------|-------------------|------------|
| `#y` | footer.html | Новый год copyright |
| `#menu-overlay` | menu_drawer.html:L1 | Overlay click close / ESC close |
| `#menu-panel` | menu_drawer.html:L5 | -translate-x-full transform drawer |
| `#menu-open` | header.html:L10 | Hamburger button open |
| `#menu-close` | menu_drawer.html:L12 | Close X button drawer |
| `#menu-loading`, `#menu-content`, `#menu-empty`, `#menu-notfound`, `#menu-notfound-text`, `#menu-stats` | menu_drawer.html L39,40,41,44,53,59 | 6 state UI elements drawer |
| `#menu-search`, `#menu-search-clear` | menu_drawer.html L28 / L32 | Filter brands by query includes |

---

## § 5. Validation P7 после записи (6 Grep-проверок)

1. **Routes grep**: все 12 HTTP URLs из reference §4.1 должны совпадать с @router.get и main.py точными строками. Проверка отсутствия опечаток /partial vs /partials.
2. **Alpine factory names**: `Alpine.data('searchLock'...)`, `Alpine.data('headerSearch'...)` — точные строки search.js. x-data= usages в base/header совпадают.
3. **PhotoSwipe 3 options**: bgOpacity=0.95, showHideAnimationType='zoom', padding 20 — VERBATIM album.html:L317-319.
4. **Tailwind design tokens**: 5 hex colors bg/surface/line/muted/ink VERBATIM match head.html config values; boxShadow card/panel strings.
5. **Reseller Protection invariant Grep**: `Select-String templates/**/*.html,src/modules/web/router.py -Pattern 'original_title|weidian_url'` → templates — 0 hits; router.py — только 1 комментарий-запрет L302-303.
6. **Jinja2 blocks scope validation**: grep `{% block.*%}` в base.html должен найти 4 блока; grep {% block в components/*.html — 0 найденных (блоки не переопределяются внутри include — scope bug, запрещено).
7. **Min 35 file:/// ссылок** по 3 файлам docs/03-web-and-frontend/

---

## § 6. Риски и миграции (Lessons mirrored from Phase4)

| Risk | Mitigation | Source |
|------|------------|--------|
| Moved Jinja2 {% block %} inside include → PhotoSwipe CSS/styles не загружены → ReferenceError. Обнаружено Phase4 PhotoSwipe debug. | Validation P7 #6 grep blocks ONLY in base.html root. | Project memory → topics.md session 6aad3 «Jinja Block Scope». |
| Alpine defer script order wrong → factories не зарегистрированы перед Alpine scan → всегда открытый search bar. Обнаружено Phase4 search bar debug. | Секция explanation 2.2 Rule #2 script execution order VERBATIM base.html:L27-L32 + HowTo Recipe 3. | Project memory → debug-search-bar-always-open.md CLOSED. |
| updatePswpAttributes called before declared → ReferenceError при HTTP-cache img onload early trigger. | explanation §2.4 Critical Protocol + reference §4.4 Data-atts + HowTo Recipe 5. | Project memory → debug-photoswipe-lightbox-broken.md CLOSED. |
| CDN Tailwind/Alpine/HTMX/PhotoSwipe sanctions-blocked → blank layout/no interactivity. | HowTo Recipe 8 self-hosting step-by-step + explanation §2.4 self-hosted comment. | User profile → self-hosting preference over CDN. |
