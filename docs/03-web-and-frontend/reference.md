# Справочник: REST API, карта шаблонов Jinja2, клиентские скрипты и .env

Аннотация: Полный перечень REST API эндпоинтов FastAPI (методы, URL, query/path params, response коды), карта всех Jinja2-шаблонов с деревом extends/include, сигнатуры клиентских Alpine.js/vanilla JS-скриптов (`search.js`, `menu.js`, `photoswipe-lightbox` init), а также исчерпывающий список всех параметров `.env` с дефолтами и примерами.

---

## 4.1 Карта HTTP Routes (web_router 11 + /health = 12 эндпоинтов)

> VERBATIM из декораторов `@router.get`/`@app.get` в [router.py:L81-L449](file:///C:/Users/Void/Desktop/yupoo-parser/src/modules/web/router.py#L81-L449) + [main.py:L163-L176](file:///C:/Users/Void/Desktop/yupoo-parser/src/main.py#L163-L176). +1 монтирование `/static` StaticFiles +1 Jinja globals.

| Метод | Path (URL) | Tags | Handler-функция | Query/Path Params | Depends() | Response Class | Строка в файле |
|-------|-----------|------|-----------------|-------------------|-----------|----------------|----------------|
| GET | `/health` | system | `health` (anonymous closure) | — | Request (читает `app.state.services`) | JSON dict `{status,templates_dir,services:{telegram_available,media_available}}` | main.py:L163 |
| GET | `/favicon.ico` | static | `favicon` (anonymous) | — | `Depends(_media_svc)` → MediaService | `FileResponse(favicon)` или 204 No Content | router.py:L81 |
| GET | `/api/menu.json` | api,menu | `api_menu_json` (anonymous) | — | `Depends(get_db_session)` → AsyncSession | JSONResponse `list[{id,name,album_count,first_letter,url}]` группированный бренды-категории | router.py:L86 |
| GET | `/` | pages | `homepage` (anonymous) | — | session + `Depends(_get_templates)` → Jinja2Templates | HTMLResponse `TemplateResponse(index.html)` + recommended_brands + latest_albums | router.py:L102 |
| GET | `/about` | pages | `about_page` (anonymous) | — | tpl + settings env globals | HTMLResponse `TemplateResponse(about.html)` manager/IG/reviews cards | router.py:L149 |
| GET | `/partial/albums` | partial | `partial_albums_grid` (anonymous) | `page:int[ge=1]`, `category_id:int\|None`, `per_page:int=36` | session + tpl | **HTMLResponse fragment** album_grid_chunk.html + `Cache-Control: private,no-store,max-age=0` | router.py:L173 |
| GET | `/category/{category_id}` | pages | `category_page` (anonymous) | `category_id:int[ge=1]`, `page:int[1..10000]=1` | session + tpl | HTMLResponse `TemplateResponse(category.html)` breadcrumbs + pluralization + grid | router.py:L226 |
| GET | `/album/{album_id}` | pages | `album_page` (anonymous) | `album_id:int[ge=1]` | session factory manual (NO Depends — custom try/except NotFound) | HTMLResponse `TemplateResponse(album.html)` OG tags + gallery + Telegram order modal | router.py:L280 |
| GET | `/search` | search | `search_page` (anonymous) | `q:str[max_len=200]`, `limit:int[1..200]=24`, `threshold:float[0..1]=0.2` | session + tpl | `302 Redirect /` при пустом q; `TemplateResponse(search.html)` при наличии запроса | router.py:L356 |
| GET | `/media/image/{image_id}` | media | `get_media_image` (anonymous) | `image_id:int[ge=1]` | session + media_svc + tg_service from `app.state.services` | Response streaming `io.BytesIO(TG file_id)`; fallback → placeholder/no-image.png | router.py:L388 |
| GET | `/api/search/suggest` | api,search | `api_search_suggest` (anonymous) | `q:str[max_len=200]` (len<3 → []), `limit:int[1..50]=8`, `threshold:float[0..1]=0.2` | session | JSONResponse `list[{id,title,image_id,url}]` top-N pg_trgm | router.py:L401 |
| **Итого HTTP routes** | — | — | — | — | — | — | **11 в web_router + /health = 12** |
| Static mount | `/static/*` | — | `_mount_static()` via `app.mount()` | subpath `/static/xxx` → resolve against STATIC_DIR | — | `StaticFiles` directory listing disabled | main.py:L136 |
| Jinja globals | — | — | `_templates()` instantiate | — | settings instance injected | `tpl.env.globals['settings'] = settings` для доступа в любом шаблоне `{{ settings.MANAGER_USERNAME }}` | main.py:L45 |

---

## 4.2 Jinja2 Blocks Inventory — только в корне base.html! (CRITICAL Protocol Scope)

> **⚠ Warning Critical Protocol (Phase4 lesson).** Jinja `{% block %}` для переопределения ОБЯЗАТЕЛЬНО объявляются ТОЛЬКО в [base.html root](file:///C:/Users/Void/Desktop/yupoo-parser/templates/base.html). **НЕ В `{% include %}`-файлах.** Блок внутри included компонента выкидывается Jinja из цепочки наследования и дочерние `{% block extra_head %}` в album.html НИКОГДА не сработают (причина PhotoSwipe bug Phase4).

| Block name | Расположение в base.html (строка) | Тип контента | Переопределяется в каких страницах | Назначение / Critical Notes |
|------------|-----------------------------------|---------------|------------------------------------|------------------------------|
| `{% block title %}` | head.html L3 (include внутри `<head>` base.html:L4) | Plain text inside `<title>` | **ALL 5 страниц** — index/category/album/search/about | `<title>` вкладки браузера. Блок находится внутри included head.html — это **ЕДИНСТВЕННОЕ исключение** из «rule no blocks inside includes»: title работает даже внутри include потому что это не пользовательский custom block scope, а текст тега. Для остальных 3 блоков правило строгое. |
| **`{% block extra_head %}`** | **base.html:L5 — ПОСЛЕ `{% include head.html %}` В КОРНЕ HEAD** | `<meta>`, `<link rel=stylesheet>`, `<script>` declaration **ДО `<body>`** | **ТОЛЬКО album.html** (PhotoSwipe CSS + updatePswpAttributes IIFE + OG meta product/image) | Самый критичный блок по Scope Protocol. В album.html сюда зашиты: (1) OG meta для красивых Telegram share превью, (2) PhotoSwipe self CSS, (3) `window.updatePswpAttributes()` IIFE ДО `<body>` (Critical Protocol для HTTP-cache img onload early trigger). |
| `{% block content %}` | base.html:L22 inside `<main>` max-w-1400 | Основной HTML-контент страницы | **ALL 5 страниц** | Единственный контейнер контента «по центру» в общем layout sticky header/footer. |
| **`{% block extra_scripts %}`** | **base.html:L32 ПЕРЕД `</body>` — ПОСЛЕ 4 core скриптов** | `<script>` (в т.ч. `<script type=module>` ESM) | **ТОЛЬКО album.html** (PhotoSwipeLightbox ESM init + capturing click preventDefault listener) | Запускается ПОСЛЕ defer search.js → defer menu.js → SYNC htmx → defer alpinejs. Гарантия: PhotoSwipe инициализируется ТОЛЬКО когда весь DOM с Alpine stateful + htmx sentinel swap уже инициализирован. |

---

## 4.3 Alpine.js Factories Stores (static/js/search.js + album inline)

> IIFE pattern idempotent registration guard в [search.js:L126-L132](file:///C:/Users/Void/Desktop/yupoo-parser/static/js/search.js#L126-L132): `if window.Alpine && typeof Alpine.data === 'function' → _register(Alpine) now; else → addEventListener('alpine:init', _register)`. Гарантия factories registration НЕ зависит от script defer order.

| Factory name (Alpine.data key) | Сигнатура `x-data='…'` в HTML | Где используется в templates | Ключевые публичные свойства / методы | Строка search.js |
|---------------------------------|--------------------------------|------------------------------|---------------------------------------|------------------|
| **`searchLock`** (scroll-lock global) | `x-data="searchLock()"` без аргументов | [base.html:L8 `<body>`](file:///C:/Users/Void/Desktop/yupoo-parser/templates/base.html#L8) — глобально на весь документ | Свойства: `searchLocked:bool` (для :class overflow-hidden), `_searchOpen:bool`, `_savedY:int`. Методы: `_isMobile() → bool` (window.innerWidth < 768), `_updateLock()` → если mobile & open → overflow-hidden + save Y; else restore `scrollTo(0, savedY)`; слушает 3 window CustomEvents. | search.js:L3-L27 |
| **`headerSearch`** (dropdown search suggest) | `x-data='headerSearch({{ initial_query\|tojson }})'` — initialQ string | [components/header.html](file:///C:/Users/Void/Desktop/yupoo-parser/templates/components/header.html) `<header>` sticky top | Свойства 22 public: `open/mobileOpen/q:str/results:list[{id,title,url,image_id}]/loading/bool/idx:int/_abort:AbortController`. Методы: `emitGlobal(ev, detail={})` → `new CustomEvent('search-open'/'search-close')`; `closeAll()/openDesktop()/openMobile()/closeMobile()`; `onInput = $debounce(300ms)` → `_doSearch()`; `_doSearch()` → `fetch('/api/search/suggest?q=…&limit=8')` AbortController on new input; `goResult(idx)` → navigate `window.location = results[idx].url`; `submitFull()` → redirect `/search?q=…`; `allUrl()` → `/search?q=` all results link. | search.js:L29-L123 |
| Inline anonymous (order modal scroll-lock coexists) | `x-data='{ orderModalOpen:false, _savedY:0, _weLocked:false, _syncScroll:function(){…} }'` | [album.html:L69-L105 `<div>`](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L69-L105) в начале content блока | Свойства: `orderModalOpen:bool` (кнопка «Заказать в Telegram» → bottomsheet/modal open close). **Guard `_weLocked:bool` Re-entrancy**: при `open` если body уже содержит overflow-hidden (searchLock его поставил) → НЕ трогаем lock, `_weLocked=false`; только если мы первые — ставим overflow + save Y `_weLocked=true`. При `close` снимаем overflow-hidden ТОЛЬКО если `_weLocked===true` — иначе searchLock продолжит держать блокировку независимо. **Coexistence protocol 2 scroll locks без конфликтов.** | album.html:L69-L105 inline (НЕ в search.js!) |

---

## 4.4 PhotoSwipe v5 Integration Reference (self-hosted ESM)

> Self-hosted факт: 3 файла живут локально в static/ вместо unpkg CDN. Причина — санкционные блокировки внешних CDN в RU/RB → blank layout risk. См [recipe how-to R8 self-hosting](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/how-to.md).

| Entity | Значение VERBATIM | Расположение в коде (строка) |
|--------|-------------------|-------------------------------|
| Self-hosted ESM Lightbox bundle | `/static/js/photoswipe-lightbox.esm.js` (1 файл) | import statement `import PhotoSwipeLightbox from '/static/js/photoswipe-lightbox.esm.js'` → [album.html:L310](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L310) |
| Self-hosted ESM Core bundle | `/static/js/photoswipe.esm.js` | pswpModule factory `() => import('/static/js/photoswipe.esm.js')` → [album.html:L315](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L315) |
| Self-hosted CSS stylesheet | `/static/css/photoswipe.css` | `<link rel=stylesheet href="/static/css/photoswipe.css">` → [album.html:L13](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L13) |
| Gallery container selector | `"#album-gallery"` | `gallery: '#album-gallery'` lightbox option → [album.html:L313](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L313). Id элемента `<div id="album-gallery">` grid контейнер. |
| Children clickable selector | `"a.pswp-link"` | `children: 'a.pswp-link'` → [album.html:L314](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L314). Каждая миниатюра галереи обёрнута в `<a class="pswp-link">`. |
| `data-pswp-src` attribute href | `"/media/image/{image_id}"` — proxied Telegram CDN endpoint | `<a class="pswp-link" data-pswp-src="/media/image/{{ image.id }}" …>` → [album.html:L139](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L139) |
| **INITIAL PLACEHOLDER** data-pswpWidth / data-pswpHeight | Hardcoded `1000` × `1000` (DOES NOT match реальному aspect!) | `data-pswpWidth="1000" data-pswpHeight="1000"` → [album.html:L141-L142](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L141-L142). **ЭТИ 1000 перезаписываются функцией updatePswpAttributes() после onload img на реальные naturalWidth/Height.** |
| Capturing click preventDefault listener | `galleryContainer.addEventListener('click', (e)=>{const l=e.target.closest('a.pswp-link'); if(l) e.preventDefault()}, true);` (capturing=true → ПЕРВЫЙ в цепочке) | [album.html:L302-L307](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L302-L307). Блокирует навигацию по href если пользователь кликает по ссылке с картинкой — PS обрабатывает клик сам. |
| **3 init options VERBATIM (no defaults override)** | 1. `padding: { top:20, bottom:20, left:20, right:20 }`<br>2. `bgOpacity: 0.95`<br>3. `showHideAnimationType: 'zoom'` | Единственные 3 non-default опции передаются в конструктор → [album.html:L317-L319](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L317-L319). |
| Debug global handle | `window.__ps_lightbox = lightbox;` (висит на window для DevTools Console manipulations) | [album.html:L323](file:///C:/Users/Void/Desktop/yupoo-parser/templates/album.html#L323). Пример: `__ps_lightbox.open(0)` — открыть лайтбокс программно на первом изображении. |

---

## 4.5 Tailwind CDN Design Tokens (inline config в components/head.html)

> No node_modules, no `tailwind.config.js`, no build step. Весь theme extend зашит в inline `<script tailwind.config = {…}>`. Поддержка изменений «из коробки» без npm на Windows-хосте. Источник: [head.html:L13-L30](file:///C:/Users/Void/Desktop/yupoo-parser/templates/components/head.html#L13-L30).

### 4.5.1 Colors hex (theme.extend.colors)

| Token name | HEX value VERBATIM | Где применяется в layout |
|------------|-------------------|--------------------------|
| `bg` | `#fafafa` | `<body>` фон страницы, `.bg-bg` класс utility. |
| `surface` | `#ffffff` | Альбом-карточки, modal, bottomsheet, drawer menu panel. `.bg-surface`. |
| `line` | `#eceff3` | Горизонтальные / вертикальные разделители `<hr>`, border карточек. `.border-line`. |
| `muted` | `#71717a` | Текст вторичный (copyright, подписи к ценам, счетчики). `.text-muted`. |
| `ink` | `#09090b` | Заголовки H1/H2, основной текст, CTA кнопки. `.text-ink`. |

### 4.5.2 Font families (theme.extend.fontFamily)

| Token name | Value array VERBATIM |
|------------|----------------------|
| `sans` | `['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif']` |
| `mono` | `['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace']` |

### 4.5.3 Box Shadows (theme.extend.boxShadow)

| Token name | Value VERBATIM (rgba CSS) | Применение |
|------------|---------------------------|------------|
| `shadow-card` | `0 10px 30px -10px rgba(0,0,0,0.15), 0 4px 12px -6px rgba(0,0,0,0.08)` | Карточки альбома в каталоге (album-card hover). |
| `shadow-panel` | `0 20px 60px -15px rgba(0,0,0,0.18), 0 8px 20px -10px rgba(0,0,0,0.10)` | Menu drawer, search suggest dropdown, modals — «глубокая» тень над контентом. |

### 4.5.4 Responsive grid breakpoints (Tailwind defaults + classes per page)

> Tailwind default screens base values: `sm ≥ 640px`, `md ≥ 768px`, `lg ≥ 1024px`, `xl ≥ 1280px`, `2xl ≥ 1536px`.

| Тип grid | Mobile (<640px) | sm (≥640) | md (≥768) | lg (≥1024) | xl (≥1280) | Где меняется одновременно (5 мест) |
|----------|-----------------|-----------|-----------|------------|------------|------------------------------------|
| Каталог альбомов (cards) | `grid-cols-2` | `sm:grid-cols-3` | `md:grid-cols-4` | `lg:grid-cols-5` | `xl:grid-cols-6` | index.html / category.html / search.html / album_grid_chunk.html (outer grid) / album_grid_chunk.html (skeleton placeholder grid) — 5 ТОЧЕК ЗАМЕНЫ ОДНОВРЕМЕННО [recipe R4](file:///C:/Users/Void/Desktop/yupoo-parser/docs/03-web-and-frontend/how-to.md) |
| Галерея альбома (images) | `grid-cols-3` | `sm:grid-cols-4` | `md:grid-cols-6` | `lg:grid-cols-8` | (no change) | ТОЛЬКО album.html:L120 gallery grid. |
| Бренды menu drawer inner | `grid-cols-2` | `sm:grid-cols-3` | (no change) | (no change) | (no change) | menu_drawer.html brands grid. |
| Hero recommended brands main pills | `grid-cols-2` | `sm:grid-cols-3` | `md:grid-cols-4` | `lg:grid-cols-5` | `xl:grid-cols-6` | index.html hero carousel snap-x section. |

---

## 4.6 Settings .env Web Frontend defaults (config.py VERBATIM)

> Источник [config.py:L66-L93](file:///C:/Users/Void/Desktop/yupoo-parser/src/core/config.py#L66-L93) BaseSettings Pydantic v2 `env_file=.env`. Значения по умолчанию задокументированы VERBATIM — NO fabrication.

| Env Key (UPPERCASE) | Default value VERBATIM | Назначение / использование в web слое |
|---------------------|------------------------|----------------------------------------|
| `MANAGER_USERNAME` | `"ManagerSem"` | Telegram username менеджера для ссылки заказать. Router формирует URL: `https://t.me/{name.lstrip('@')}?text=…` с префиллом сообщения. |
| `TELEGRAM_ORDER_MESSAGE` | `'Здравствуйте! Хочу заказать этот товар: "{title}". Ссылка: {url}'` | Python format-строка для prefill текста в Telegram URL при клике «Заказать в Telegram». `title` = `detail.clean_title` (Reseller Protection NO original_title). `url` = `request.url` альбом page. |
| `INSTAGRAM_USERNAME` | `"semsneak"` | Instagram username для карточки «Написать в Direct» на about.html + footer link. Формирует `https://ig.me/m/{name}`. |
| `REVIEWS_CHANNEL_URL` | `""` (empty string) | URL публичного Telegram-канала с отзывами покупателей. Если пустая строка (дефолт) — **скрывается UI элемент целиком** на about.html карточке + в footer (no «Отзывы» button). Пример env значения: `https://t.me/+XXXXXXXXXX`. |
| `RECOMMENDED_BRANDS` | `""` (empty string = пустой карусель на главной) | CSV список рекомендуемых брендов. Валидируется validator `UPPERCASE` → все записи приводятся к вернему регистру при парсинге. Разделитель `,`. **Пример env:** `RECOMMENDED_BRANDS=NIKE,ADIDAS,JORDAN,ARCTERYX,BALENCIAGA,STONE ISLAND` → 6 pill-брендов в hero carousel index.html. Helper `get_recommended_brands()` → `list[str]` UPPER. |

---

## 4.7 HTMX Partial endpoint reference (sentinel attributes + swap strategy)

> Единственный HTMX partial endpoint в проекте: `/partial/albums`. Shared fragment `album_grid_chunk.html` переиспользуется index/category/search страницами. NO client-side fetch, NO client-side state pagination offset.

| Item | Значение VERBATIM | Строка |
|------|-------------------|--------|
| Endpoint URL | `GET /partial/albums?page={N:int}&category_id={int\|missing}&per_page=36` | router.py:L173 |
| HTTP Cache-Control response header | `private, no-store, max-age=0` (no browser cache, no CDN cache) | router.py:L220 `response.headers['Cache-Control']` |
| **hx-sentinel HTML attributes** (outer div `.hx-sentinel-wrap`) | `hx-get="{{ next_url }}"`<br>`hx-trigger="revealed"`<br>`hx-swap="outerHTML show:none scroll:none"`<br>`hx-target="closest div.hx-sentinel-wrap"`<br>`hx-indicator=".htmx-sentinel-indicator-{{ page }}"` | album_grid_chunk.html:L55-L62 |
| Swap strategy semantic | **outerHTML самого sentinel wrapper.** Почему: (1) удаляется текущий div.hx-sentinel-wrap + его 36 карточек + его индикатор loading целиком, (2) в DOM вставляется ответ, содержащий НОВЫЙ div.hx-sentinel-wrap для следующей страницы page+1 с новым hx-get URL, (3) нет дублирования карточек, нет лишних обёрток. | — |
| `show:none scroll:none` в hx-swap значении | Почему: `show:none` — НЕ скроллить viewport автоматически к появившемуся контенту (бесконечный скролл должен быть незаметным для пользователя, скролл идёт естественно от движения колеса мыши / пальца). `scroll:none` — отключает автоматическую прокрутку к самому элементу. | album_grid_chunk.html:L59 |
| Indicator visibility CSS hook | `.htmx-request .htmx-indicator { opacity: 1; display: grid; }` — когда sentinel находится в состоянии `htmx-request` (ждём ответ сервера) → skeleton карточки 6 штук `.htmx-indicator opacity-0` становятся видимыми. | head.html:L21-L26 `.htmx-indicator` CSS rule. |
| has_next False termination | Если `has_next == False` в response контексте → sentinel `.hx-sentinel-wrap` в ответе **НЕ содержит hx-get/hx-trigger** атрибуты. Вместо него рендерится текст: `✅ Вы просмотрели все товары в этой категории.` Цикл бесконечного скролла завершается. | album_grid_chunk.html conditional render. |

---

## 4.8 Vanilla JS menu.js DOM Element IDs (жестко зашитые строки getElementById)

> 13 строк VERBATIM `document.getElementById('X')` в menu.js. **НЕ ПЕРЕИМЕНОВЫВАЙТЕ ЭТИ ID В HTML — меню drawer сломается.** Источник: grep getElementById по menu.js.

| getElementById строка (case-sensitive!) | Расположение HTML шаблона | Назначение | Строка menu.js |
|------------------------------------------|---------------------------|------------|-----------------|
| `"y"` | [components/footer.html](file:///C:/Users/Void/Desktop/yupoo-parser/templates/components/footer.html) `<span id="y">YYYY</span>` | Динамический год copyright footer `new Date().getFullYear()`. | menu.js:L2 |
| `"menu-overlay"` | [components/menu_drawer.html:L1](file:///C:/Users/Void/Desktop/yupoo-parser/templates/components/menu_drawer.html#L1) `<div id="menu-overlay" …>` | Backdrop overlay drawer. Клик по overlay → closeMenu. ESC → click overlay synthetic. | menu.js:L5 |
| `"menu-panel"` | menu_drawer.html:L5 `<aside id="menu-panel" …>` | Сам drawer панель. CSS class `.translate-x-full` transform скрывает/показывает. rAF + transition 180ms. | menu.js:L6 |
| `"menu-open"` | [components/header.html:L10](file:///C:/Users/Void/Desktop/yupoo-parser/templates/components/header.html#L10) hamburger `<button id="menu-open" …>` | Кнопка открытия меню в header (левый верхний угол). addEventListener click → openMenu. | menu.js:L7 |
| `"menu-close"` | menu_drawer.html:L12 `<button id="menu-close" …>` | Крестик закрытия внутри drawer панели. click → closeMenu. | menu.js:L8 |
| `"menu-loading"` | menu_drawer.html:L39 `<div id="menu-loading" …>` | Spinner-состояние пока fetch `/api/menu.json`. first open lazy fetcher. | menu.js:L9 |
| `"menu-content"` | menu_drawer.html:L40 `<div id="menu-content" …>` | Основной render div с брендами / категориями groupByLetter. | menu.js:L10 |
| `"menu-empty"` | menu_drawer.html:L41 `<div id="menu-empty" …>` | State «В базе пока нет товаров — идёт парсинг». Empty DB scenario. | menu.js:L11 |
| `"menu-notfound"` | menu_drawer.html:L44 `<div id="menu-notfound" …>` | State «ничего не найдено по вашему запросу фильтра» в drawer поиске брендов. | menu.js:L12 |
| `"menu-notfound-text"` | menu_drawer.html:L53 `<span id="menu-notfound-text">…</span>` | Динамический текст «По запросу "КРОССЫ" ничего не найдено.» с пользовательским input. | menu.js:L13 |
| `"menu-stats"` | menu_drawer.html:L59 footer `<div id="menu-stats" …>` | Статистика: «N брендов, M категорий, K альбомов.» после группировки. | menu.js:L14 |
| `"menu-search"` | menu_drawer.html:L28 `<input id="menu-search" type="search" …>` | Текстовый input фильтра брендов внутри drawer (vanilla includes() filter substring match). input event listener → filterMenu. | menu.js:L15 |
| `"menu-search-clear"` | menu_drawer.html:L32 `<button id="menu-search-clear" …>` | Кнопка «× очистить фильтр». click → очистить input.value → show all brands again. | menu.js:L16 |

---

## 4.9 Константы роутера (invariant literals router.py header)

> Hardcoded литералы constants в web router. Не вынесены в Settings потому что меняются ТОЛЬКО при рефакторе макета layout.

| Константа имя (вербальный) | Значение VERBATIM | Строка router.py | Где используется |
|----------------------------|-------------------|------------------|------------------|
| `_INFINITE_SCROLL_PER_PAGE` module level (as assignment, no global export single location) | `36` | router.py:L18 объявление default value, L200 вызов paginate() | `/partial/albums` endpoint `/category/{id}` endpoint `/` homepage latest album list. 36 карточек = grid-cols-6 (xl desktop) × 6 рядов полностью заполненных страниц. |
| `PLACEHOLDER_FILENAME` | `"no-image.png"` | router.py:L19 module level literal | `og_image` fallback when cover_image_id=None. Media endpoint `/media/image/{id}` TG failure fallback → StaticFiles serve `/static/images/no-image.png`. |
| `api_search_suggest limit default` | `8` | router.py:L408 `limit:int=8` | Header search `/api/search/suggest?q=…` → JS headerSearch _doSearch. Максимально 8 результатов dropdown. |
| `api_search_suggest limit max` | `50` | router.py:L408 `limit:int=Field(8, ge=1, le=50)` | Верхняя граница пользовательского limit parameter (validation 422 если >50). |
| `search_page limit default` | `24` | router.py:L363 `limit:int=24` | `/search` results default items per page (grid-cols-6 × 4 rows = 24). |
| `_search_page_min_query_len_trigger` implicit in suggest endpoint | `3` | router.py:L422 `if len(q) < 3: return []` | Триграммный поиск FTS НЕ запускается для коротких фраз (пользователь ещё печатает NI → выдаёт пустой массив). |
