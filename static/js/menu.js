document.addEventListener('DOMContentLoaded', function () {
  var yEl = document.getElementById('y');
  if (yEl) yEl.textContent = new Date().getFullYear();

  var overlay = document.getElementById('menu-overlay');
  var panel = document.getElementById('menu-panel');
  var openBtn = document.getElementById('menu-open');
  var closeBtn = document.getElementById('menu-close');
  var loading = document.getElementById('menu-loading');
  var contentEl = document.getElementById('menu-content');
  var emptyEl = document.getElementById('menu-empty');
  var notfoundEl = document.getElementById('menu-notfound');
  var notfoundText = document.getElementById('menu-notfound-text');
  var statsEl = document.getElementById('menu-stats');
  var searchInput = document.getElementById('menu-search');
  var searchClearBtn = document.getElementById('menu-search-clear');
  var loaded = false;

  function openMenu() {
    if (!overlay) return;
    overlay.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    requestAnimationFrame(function () {
      overlay.classList.remove('opacity-0');
      if (panel) panel.classList.remove('-translate-x-full');
    });
    if (!loaded) loadMenu();
  }

  function closeMenu() {
    if (!overlay) return;
    overlay.classList.add('opacity-0');
    if (panel) panel.classList.add('-translate-x-full');
    setTimeout(function () {
      overlay.classList.add('hidden');
      document.body.style.overflow = '';
    }, 180);
  }

  if (openBtn) openBtn.addEventListener('click', openMenu);
  if (closeBtn) closeBtn.addEventListener('click', closeMenu);
  if (overlay) overlay.addEventListener('click', function (e) { if (e.target === overlay) closeMenu(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && overlay && !overlay.classList.contains('hidden')) closeMenu();
  });

  function _esHtml(s) {
    return String(s == null ? '' : s)
      .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  }

  function filterMenu(query) {
    var q = (query || '').trim().toLowerCase();
    var rows = contentEl ? contentEl.querySelectorAll('[data-letter-row]') : [];
    var visibleBrands = 0;
    var totalBrands = 0;
    rows.forEach(function (row) {
      var links = row.querySelectorAll('[data-brand-name]');
      var hasVisible = false;
      links.forEach(function (a) {
        totalBrands++;
        var name = (a.getAttribute('data-brand-name') || '').toLowerCase();
        var ok = q.length === 0 || name.includes(q);
        a.classList.toggle('hidden', !ok);
        if (ok) { hasVisible = true; visibleBrands++; }
      });
      row.classList.toggle('hidden', !hasVisible);
    });
    if (!q) {
      if (notfoundEl) notfoundEl.classList.add('hidden');
      if (emptyEl) emptyEl.classList.toggle('hidden', totalBrands !== 0);
      if (statsEl) statsEl.textContent = (totalBrands || 0) + ' брендов';
      return;
    }
    if (emptyEl) emptyEl.classList.add('hidden');
    if (visibleBrands === 0) {
      if (notfoundEl) notfoundEl.classList.remove('hidden');
      if (notfoundText) notfoundText.textContent = 'Бренды по запросу \u201C' + query.trim() + '\u201D не найдены';
      if (statsEl) statsEl.textContent = '0 / ' + totalBrands + ' брендов';
    } else {
      if (notfoundEl) notfoundEl.classList.add('hidden');
      if (statsEl) statsEl.textContent = visibleBrands + ' / ' + totalBrands + ' брендов';
    }
  }

  if (searchInput) {
    searchInput.addEventListener('input', function (e) {
      var v = e.target && e.target.value;
      if (searchClearBtn) searchClearBtn.classList.toggle('hidden', !v);
      filterMenu(v);
    });
    searchInput.addEventListener('focus', function () {
      if (!loaded) loadMenu();
    });
  }
  if (searchClearBtn) {
    searchClearBtn.addEventListener('click', function () {
      if (!searchInput) return;
      searchInput.value = '';
      searchClearBtn.classList.add('hidden');
      filterMenu('');
      searchInput.focus({ preventScroll: true });
    });
  }

  function groupByLetter(children) {
    var map = new Map();
    (children || []).forEach(function (c) {
      var key = c.first_letter || '#';
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(c);
    });
    return Array.from(map.entries()).sort(function (pairA, pairB) {
      var a = pairA[0]; var b = pairB[0];
      var isEng = function (char) { return (/^[A-Z]$/i).test(char); };
      var isRus = function (char) { return (/^[А-ЯЁ]$/i).test(char); };
      var score = function (char) {
        if (isEng(char)) return 1;
        if (isRus(char)) return 2;
        return 3;
      };
      var scoreA = score(a);
      var scoreB = score(b);
      if (scoreA !== scoreB) {
        return scoreA - scoreB;
      }
      return a.localeCompare(b, 'ru');
    });
  }

  async function loadMenu() {
    loaded = true;
    try {
      var r = await fetch('/api/menu.json', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      var categories = await r.json();
      if (loading) loading.classList.add('hidden');
      if (!categories || !categories.length) {
        if (emptyEl) emptyEl.classList.remove('hidden');
        return;
      }
      if (contentEl) contentEl.classList.remove('hidden');
      var frag = document.createDocumentFragment();
      var total = categories.length;

      var section = document.createElement('section');
      section.className = 'border-b border-line last:border-b-0';
      var head = document.createElement('div');
      head.className = 'px-6 pt-6 pb-3 flex items-end justify-between gap-3';
      head.innerHTML = '<h3 class="font-sans font-bold text-lg tracking-tight"></h3>' +
                        '<span class="text-[10px] uppercase tracking-[0.2em] text-muted whitespace-nowrap"></span>';
      head.querySelector('h3').textContent = 'Все бренды';
      head.querySelectorAll('span')[0].textContent = total + ' брендов';
      section.appendChild(head);

      var body = document.createElement('div');
      body.className = 'px-6 pb-6';
      groupByLetter(categories).forEach(function (pair) {
        var letter = pair[0]; var list = pair[1];
        var row = document.createElement('div');
        row.className = 'mb-4 last:mb-0';
        row.setAttribute('data-letter-row', letter);
        var lh = document.createElement('div');
        lh.className = 'flex items-center gap-3 mb-2';
        lh.innerHTML = '<div class="w-6 h-6 rounded-full bg-black text-white inline-flex items-center justify-center font-mono font-bold text-[11px]"></div>' +
                        '<div class="text-[10px] uppercase tracking-[0.25em] text-muted"></div>';
        lh.querySelector('div').textContent = letter;
        row.appendChild(lh);
        var grid = document.createElement('div');
        grid.className = 'grid grid-cols-2 sm:grid-cols-3 gap-1.5 ml-9';
        list.forEach(function (c) {
          var a = document.createElement('a');
          a.href = c.url;
          a.className = 'group flex items-center justify-between px-3 py-2 rounded-lg text-sm hover:bg-bg border border-transparent hover:border-line transition';
          if (!c.album_count) a.classList.add('opacity-40');
          a.setAttribute('data-brand-name', _esHtml(c.name || ''));
          a.innerHTML = '<span class="truncate font-medium"></span>' +
                         '<span class="ml-2 text-[11px] text-muted font-mono tabular-nums"></span>';
          a.querySelector('span').textContent = c.name;
          a.querySelectorAll('span')[1].textContent = c.album_count;
          grid.appendChild(a);
        });
        row.appendChild(grid);
        body.appendChild(row);
      });
      section.appendChild(body);
      frag.appendChild(section);

      contentEl.innerHTML = '';
      contentEl.appendChild(frag);
      if (searchInput && searchInput.value) {
        filterMenu(searchInput.value);
      } else {
        filterMenu('');
      }
    } catch (e) {
      if (loading) loading.innerHTML = '<span class="text-rose-500 text-sm">Не удалось загрузить меню: ' + (e && e.message ? e.message : 'unknown') + '</span>';
    }
  }
});
