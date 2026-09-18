(function () {
  function _register(Alpine) {
    Alpine.data('searchLock', function () {
      return {
        searchLocked: false,
        _searchOpen: false,
        _isMobile: function () { return window.innerWidth < 768; },
        _updateLock: function () {
          var shouldLock = this._isMobile() && this._searchOpen;
          if (this.searchLocked === shouldLock) return;
          this.searchLocked = shouldLock;
          if (this.searchLocked) {
            document.body.dataset.savedScrollY = String(window.scrollY || 0);
            document.body.style.top = '-' + (window.scrollY || 0) + 'px';
            document.body.style.position = 'fixed';
            document.body.style.width = '100%';
          } else {
            var savedY = parseInt(document.body.dataset.savedScrollY || '0', 10);
            document.body.style.position = '';
            document.body.style.top = '';
            document.body.style.width = '';
            delete document.body.dataset.savedScrollY;
            window.scrollTo(0, savedY);
          }
        }
      };
    });

    Alpine.data('headerSearch', function (initialQ) {
      return {
        open: false,
        mobileOpen: false,
        q: (typeof initialQ === 'undefined' || initialQ === null || initialQ === undefined) ? '' : String(initialQ),
        results: [],
        loading: false,
        idx: -1,
        _abort: null,
        emitGlobal: function (ev, detail) {
          try { document.dispatchEvent(new CustomEvent(ev, { detail: detail || {} })); } catch (_) {}
        },
        closeAll: function () {
          this.open = false;
          this.mobileOpen = false;
          this.emitGlobal('search-close');
          this.loading = false;
          this.results = [];
          this.idx = -1;
          try { if (this._abort) { this._abort.abort(); this._abort = null; } } catch (_) {}
        },
        openDesktop: function () {
          this.open = true;
          this.emitGlobal('search-open');
          this.idx = -1;
          if ((this.q || '').trim().length >= 3 && this.results.length === 0) this.onInput();
        },
        openMobile: function ($nextTick) {
          var self = this;
          this.mobileOpen = true;
          this.open = true;
          this.emitGlobal('search-open');
          this.idx = -1;
          $nextTick(function () {
            var el = document.getElementById('mobile-search-input');
            if (el) { el.focus(); if (el.select) el.select(); }
          });
          if ((this.q || '').trim().length >= 3 && this.results.length === 0) this.onInput();
        },
        closeMobile: function () {
          this.open = false;
          this.mobileOpen = false;
          this.emitGlobal('search-close');
          this.loading = false;
          this.results = [];
          this.idx = -1;
          try { if (this._abort) { this._abort.abort(); this._abort = null; } } catch (_) {}
        },
        onInput: function () {
          this.idx = -1;
          var val = (this.q || '').trim();
          if (val.length < 3) {
            this.results = [];
            this.loading = false;
            try { if (this._abort) { this._abort.abort(); this._abort = null; } } catch (_) {}
            return;
          }
          this.loading = true;
          try { if (this._abort) { this._abort.abort(); this._abort = null; } } catch (_) {}
          this._doSearch(val);
        },
        _doSearch: async function (val) {
          var self = this;
          try {
            var ctrl = new AbortController();
            this._abort = ctrl;
            var r = await fetch(
              '/api/search/suggest?q=' + encodeURIComponent(val) + '&limit=8',
              { signal: ctrl.signal, cache: 'no-store' }
            );
            if (!r.ok) throw new Error('HTTP ' + r.status);
            this.results = (await r.json()) || [];
          } catch (e) {
            if (!(e && e.name === 'AbortError')) this.results = [];
          } finally {
            this.loading = false;
            this._abort = null;
          }
        },
        goResult: function () {
          if (this.idx >= 0 && this.idx < this.results.length) {
            var u = (this.results[this.idx] && this.results[this.idx].url) || null;
            if (u) { var url = u; this.closeAll(); window.location.href = url; return; }
          }
          this.submitFull();
        },
        submitFull: function () {
          var val = (this.q || '').trim();
          var url = '/search?q=' + encodeURIComponent(val);
          this.closeAll();
          window.location.href = url;
        },
        allUrl: function () { return '/search?q=' + encodeURIComponent((this.q || '').trim()); }
      };
    });
  }

  if (window.Alpine && typeof window.Alpine.data === 'function') {
    _register(window.Alpine);
  } else {
    document.addEventListener('alpine:init', function () {
      if (window.Alpine) _register(window.Alpine);
    });
  }
})();
