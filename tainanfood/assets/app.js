/* 台南美食通 — 靜態站共用前端
   頁面內容全部由 build_static.py 產生在 HTML 裡；這支只負責互動：
   深淺色、收藏、列表篩選排序、地圖、必比登年份篩選、舊網址轉址。 */
(function () {
  'use strict';
  var store = {
    get: function (k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };

  /* ---------- 深淺色 ---------- */
  var root = document.documentElement;
  var saved = store.get('tnf-theme', null);
  if (saved) root.dataset.theme = saved;
  var tb = document.getElementById('themeBtn');
  if (tb) tb.onclick = function () {
    var dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = dark ? 'light' : 'dark';
    store.set('tnf-theme', root.dataset.theme);
  };

  /* ---------- 收藏（localStorage，僅此裝置） ---------- */
  var favs = new Set(store.get('tnf-favs', []));
  function paint(btn) {
    var on = favs.has(btn.dataset.fav);
    btn.classList.toggle('on', on);
    btn.setAttribute('aria-label', on ? '取消收藏' : '加入收藏');
    btn.querySelector('svg').setAttribute('fill', on ? 'currentColor' : 'none');
  }
  document.querySelectorAll('[data-fav]').forEach(paint);
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-fav]');
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    var id = b.dataset.fav;
    favs.has(id) ? favs.delete(id) : favs.add(id);
    store.set('tnf-favs', [...favs]);
    document.querySelectorAll('[data-fav="' + CSS.escape(id) + '"]').forEach(paint);
    if (document.body.dataset.page === 'fav') applyFilters();
  });

  /* ---------- 列表／收藏頁：篩選與排序 ---------- */
  /* 現在是否營業：data-periods 形如 "1|0500-1|1300;2|0500-2|1300"，跨夜時結束日不同 */
  function openNow(spec) {
    if (!spec) return false;
    var now = new Date(), day = now.getDay(), mins = now.getHours() * 60 + now.getMinutes();
    return spec.split(';').some(function (seg) {
      var m = seg.match(/^(\d)\|(\d{2})(\d{2})-(\d)\|(\d{2})(\d{2})$/);
      if (!m) return false;
      var od = +m[1], ot = +m[2] * 60 + +m[3], cd = +m[4], ct = +m[5] * 60 + +m[6];
      if (od === cd) return day === od && mins >= ot && mins < ct;
      // 跨夜：開店日的開店時間之後，或收店日的收店時間之前
      return (day === od && mins >= ot) || (day === cd && mins < ct);
    });
  }

  var grid = document.getElementById('grid');
  var favPage = document.body.dataset.page === 'fav';
  function val(id) { var el = document.getElementById(id); return el ? (el.type === 'checkbox' ? el.checked : el.value) : ''; }
  function applyFilters() {
    if (!grid) return;
    var q = (val('fq') || '').trim(), cat = val('fc'), dist = val('fd'), sort = val('fs') || 'rating';
    var gem = val('fg'), bib = val('fb'), open = val('fo'), words = q ? q.split(/\s+/) : [];
    var cards = [].slice.call(grid.children), shown = 0;
    cards.forEach(function (c) {
      var d = c.dataset;
      var ok = (!cat || d.cat === cat) && (!dist || d.district === dist) &&
        (!gem || d.gem === '1') && (!bib || d.bib === '1') && (!open || openNow(d.periods)) &&
        (!favPage || favs.has(d.id)) &&
        words.every(function (w) { return d.text.indexOf(w) >= 0; });
      c.hidden = !ok;
      if (ok) shown++;
    });
    var key = { rating: 'rating', reviews: 'reviews', editor: 'editor' }[sort];
    cards.sort(function (a, b) {
      if (sort === 'old') return (+a.dataset.since || 9999) - (+b.dataset.since || 9999);
      return (+b.dataset[key] || 0) - (+a.dataset[key] || 0);
    }).forEach(function (c) { grid.appendChild(c); });
    var cnt = document.getElementById('count');
    if (cnt) cnt.textContent = shown + ' 家';
    var empty = document.getElementById('empty');
    if (empty) empty.hidden = shown > 0;
    // 讓篩選結果可以複製網址分享
    var p = new URLSearchParams();
    if (q) p.set('q', q); if (cat) p.set('cat', cat); if (dist) p.set('d', dist);
    if (sort !== 'rating') p.set('sort', sort); if (gem) p.set('gem', '1'); if (bib) p.set('bib', '1');
    if (open) p.set('open', '1');
    history.replaceState(null, '', location.pathname + (p.toString() ? '?' + p : ''));
  }
  if (grid) {
    var qs = new URLSearchParams(location.search);
    [['fq', 'q'], ['fc', 'cat'], ['fd', 'd'], ['fs', 'sort']].forEach(function (pair) {
      var el = document.getElementById(pair[0]);
      if (el && qs.get(pair[1])) el.value = qs.get(pair[1]);
    });
    [['fg', 'gem'], ['fb', 'bib'], ['fo', 'open']].forEach(function (pair) {
      var el = document.getElementById(pair[0]);
      if (el && qs.get(pair[1]) === '1') el.checked = true;
    });
    ['fc', 'fd', 'fs', 'fg', 'fb', 'fo'].forEach(function (id) {
      var el = document.getElementById(id); if (el) el.onchange = applyFilters;
    });
    var fq = document.getElementById('fq');
    if (fq) {
      fq.oninput = applyFilters;
      if (fq.form) fq.form.onsubmit = function (e) { e.preventDefault(); applyFilters(); };
    }
    applyFilters();
  }

  /* ---------- 必比登年份篩選 ---------- */
  document.querySelectorAll('[data-bibyear]').forEach(function (btn) {
    btn.onclick = function (e) {
      e.preventDefault();
      var y = btn.dataset.bibyear;
      document.querySelectorAll('[data-bibyear]').forEach(function (b) { b.classList.toggle('on', b === btn); });
      document.querySelectorAll('#bibrows tr').forEach(function (tr) {
        tr.hidden = !!y && tr.dataset.years.indexOf(y) < 0;
      });
      var note = document.getElementById('bibnote');
      if (note) { note.textContent = note.dataset['y' + y] || ''; note.hidden = !note.textContent; }
    };
  });

  /* ---------- 地圖（Leaflet，載不到就顯示說明） ---------- */
  function tiles() {
    return L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' });
  }
  var mini = document.getElementById('minimap');
  if (mini && window.L) {
    var lat = +mini.dataset.lat, lng = +mini.dataset.lng;
    var m = L.map('minimap', { zoomControl: false, scrollWheelZoom: false }).setView([lat, lng], 16);
    tiles().addTo(m); L.marker([lat, lng]).addTo(m);
  }
  var big = document.getElementById('bigmap');
  if (big) {
    if (!window.L) { big.innerHTML = '<div class="empty">地圖需要網路連線才能載入。</div>'; }
    else {
      var map = L.map('bigmap').setView([22.993, 120.204], 13);
      tiles().addTo(map);
      var all = (window.TNF_POINTS || []), markers = [], pts = [];
      all.forEach(function (p) {
        var mk = L.marker([p.lat, p.lng]).bindPopup(
          '<b>' + p.name + '</b><br>' + p.cat + (p.bib ? ' ・必比登' : '') + '<br><a href="' + p.url + '">看介紹 →</a>');
        mk.cat = p.cat; markers.push(mk); mk.addTo(map); pts.push([p.lat, p.lng]);
      });
      if (pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 15 });
      document.querySelectorAll('[data-mapcat]').forEach(function (chip) {
        chip.onclick = function (e) {
          e.preventDefault();
          var c = chip.dataset.mapcat, box = [];
          document.querySelectorAll('[data-mapcat]').forEach(function (x) { x.classList.toggle('on', x === chip); });
          markers.forEach(function (mk) {
            var show = !c || mk.cat === c;
            show ? mk.addTo(map) : map.removeLayer(mk);
            if (show) box.push(mk.getLatLng());
          });
          if (box.length) map.fitBounds(box, { padding: [30, 30], maxZoom: 16 });
        };
      });
    }
  }

  /* ---------- 舊的單頁版網址 #/r/<id> → 新的靜態頁 ---------- */
  var h = location.hash;
  if (h.indexOf('#/r/') === 0 && document.body.dataset.page === 'home') {
    location.replace('r/' + encodeURIComponent(h.slice(4).split('?')[0]) + '/');
  } else if (h === '#/list' || h.indexOf('#/list?') === 0) { location.replace('list/' + h.slice(6));
  } else if (h.indexOf('#/map') === 0) { location.replace('map/');
  } else if (h.indexOf('#/bib') === 0) { location.replace('bib/');
  } else if (h.indexOf('#/fav') === 0) { location.replace('fav/'); }

  /* ---------- PWA ---------- */
  if ('serviceWorker' in navigator && location.protocol.indexOf('http') === 0) {
    navigator.serviceWorker.register(document.body.dataset.sw || 'sw.js').catch(function () {});
  }
})();
