/* 健康美食之旅：把勾選的料理加進本日菜單，統計鈉／鉀／蛋白質／熱量／磷，並依身分給建議。
   資料只存在這台裝置的 localStorage，不會上傳。*/
(function () {
  'use strict';
  var KEY = 'tnf-menu', PROFILE = 'tnf-profile';
  var S = {
    get: function (k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set: function (k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };

  /* 參考值：一般成人依國健署／衛福部建議；CKD 與透析為臨床常見範圍，
     蛋白質與熱量以體重計算。這些是衛教用的一般參考，不是個人化處方。 */
  var REF = {
    normal: {
      label: '一般成人', na: 2300, k: 3500, phos: 1000,
      protein: function (w) { return [w * 0.9, w * 1.2]; }, kcal: function (w) { return [w * 25, w * 30]; },
      note: '鈉是唯一所有人都該留意的項目；鉀與磷在腎功能正常時由腎臟自行調節，不需刻意限制。'
    },
    ckd: {
      label: 'CKD 第 3–4 期（未透析）', na: 2000, k: 2500, phos: 800,
      protein: function (w) { return [w * 0.6, w * 0.8]; }, kcal: function (w) { return [w * 30, w * 35]; },
      note: '蛋白質採低蛋白飲食範圍（0.6–0.8 g/kg）；限鉀通常在 eGFR 低於 30、限磷在 eGFR 低於 45 之後才需要嚴格執行，請依你的抽血報告與醫囑調整。'
    },
    hd: {
      label: '血液透析中', na: 2000, k: 2000, phos: 1000,
      protein: function (w) { return [w * 1.0, w * 1.2]; }, kcal: function (w) { return [w * 30, w * 35]; },
      note: '透析會流失蛋白質，需求反而比一般人高；但鉀與磷要嚴格控制，湯汁、內臟、加工肉要特別小心。'
    }
  };

  var menu = S.get(KEY, []);          // [{id, shop, dish, nutrition}]
  var prof = S.get(PROFILE, { mode: 'normal', weight: 60 });

  function totals() {
    return menu.reduce(function (t, m) {
      var n = m.n || {};
      t.kcal += n.kcal || 0; t.protein += n.protein_g || 0;
      t.na += n.na_mg || 0; t.k += n.k_mg || 0; t.phos += n.phos_mg || 0;
      return t;
    }, { kcal: 0, protein: 0, na: 0, k: 0, phos: 0 });
  }

  function add(btn) {
    var d = btn.dataset;
    if (menu.some(function (m) { return m.key === d.key; })) return remove(d.key);
    menu.push({ key: d.key, shop: d.shop, dish: d.dish, url: d.url, n: JSON.parse(d.n || '{}') });
    S.set(KEY, menu); paintButtons(); render(); toast(d.dish + ' 已加入本日菜單');
  }
  function remove(key) {
    menu = menu.filter(function (m) { return m.key !== key; });
    S.set(KEY, menu); paintButtons(); render();
  }
  function paintButtons() {
    document.querySelectorAll('[data-addmenu]').forEach(function (b) {
      var on = menu.some(function (m) { return m.key === b.dataset.key; });
      b.classList.toggle('on', on);
      b.textContent = on ? '✓ 已在本日菜單' : '＋ 加入本日菜單';
    });
    var c = document.getElementById('menuCount');
    if (c) { c.textContent = menu.length; c.hidden = !menu.length; }
  }
  function toast(msg) {
    var t = document.createElement('div');
    t.className = 'toast'; t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2200);
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-addmenu]');
    if (b) { e.preventDefault(); add(b); return; }
    var r = e.target.closest('[data-delmenu]');
    if (r) { e.preventDefault(); remove(r.dataset.delmenu); }
  });

  /* ---------- 規劃頁 ---------- */
  function bar(label, val, max, unit, warn) {
    var pct = Math.min(100, max ? val / max * 100 : 0);
    var over = max && val > max;
    return '<div class="nrow"><span class="nlab">' + label + '</span>' +
      '<span class="nbar"><i style="width:' + pct + '%;background:' + (over ? 'var(--red)' : warn ? 'var(--gold)' : 'var(--jade)') + '"></i></span>' +
      '<b>' + Math.round(val).toLocaleString() + ' ' + unit + '</b>' +
      '<small>' + (max ? '／' + Math.round(max).toLocaleString() : '') + '</small></div>';
  }

  function advise(t, ref, w) {
    var out = [], pr = ref.protein(w), kc = ref.kcal(w);
    var pct = function (v, m) { return Math.round(v / m * 100); };
    if (t.na > ref.na) out.push(['warn', '鈉已達參考上限的 ' + pct(t.na, ref.na) + '%。台南小吃的鈉多半藏在湯汁與醬料裡——湯留一半、滷汁少淋，通常就能少掉三到四成。']);
    else if (t.na > ref.na * 0.7) out.push(['ok', '鈉接近一天的參考量（' + pct(t.na, ref.na) + '%），今天其餘兩餐建議以清淡為主。']);
    else out.push(['good', '鈉控制得不錯，只佔參考量的 ' + pct(t.na, ref.na) + '%。']);

    if (ref.label !== '一般成人') {
      if (t.k > ref.k) out.push(['warn', '鉀超過參考量（' + Math.round(t.k) + ' mg）。肉類、內臟、香菇、竹筍與湯汁都是高鉀來源，湯不喝完是最有效的一招。']);
      else if (t.k > ref.k * 0.7) out.push(['ok', '鉀已用掉 ' + pct(t.k, ref.k) + '%，其餘餐次避開果汁、芋頭、地瓜與濃湯。']);
      if (t.phos > ref.phos) out.push(['warn', '磷偏高（' + Math.round(t.phos) + ' mg）。香腸熟肉、內臟、加工食品的磷吸收率特別高，若有服用磷結合劑請記得隨餐服用。']);
    }

    if (t.protein < pr[0]) out.push(['ok', '蛋白質 ' + Math.round(t.protein) + ' g，低於你這個身分的建議範圍（' + Math.round(pr[0]) + '–' + Math.round(pr[1]) + ' g）。' + (ref.label === '血液透析中' ? '透析會流失蛋白質，吃不夠反而容易營養不良。' : '')]);
    else if (t.protein > pr[1]) out.push([ref.label === '一般成人' ? 'ok' : 'warn', '蛋白質 ' + Math.round(t.protein) + ' g，高於建議範圍上限（' + Math.round(pr[1]) + ' g）。' + (ref.label === 'CKD 第 3–4 期（未透析）' ? '低蛋白飲食有助延緩腎功能下降，可把肉類份量分一半給同行的人。' : '')]);
    else out.push(['good', '蛋白質 ' + Math.round(t.protein) + ' g，落在建議範圍內（' + Math.round(pr[0]) + '–' + Math.round(pr[1]) + ' g）。']);

    if (t.kcal && t.kcal < kc[0] * 0.5) out.push(['good', '熱量 ' + Math.round(t.kcal) + ' kcal，約佔一天所需的 ' + pct(t.kcal, kc[1]) + '%，還有空間安排其他餐次。']);
    else if (t.kcal > kc[1]) out.push(['warn', '熱量已超過一天所需（' + Math.round(t.kcal) + ' kcal），建議分兩天吃，或和同行的人分食。']);
    return out;
  }

  function render() {
    var box = document.getElementById('plan');
    if (!box) return;
    var ref = REF[prof.mode], w = +prof.weight || 60, t = totals(), pr = ref.protein(w), kc = ref.kcal(w);
    var rows = menu.map(function (m) {
      var n = m.n || {};
      return '<tr><td><b>' + m.dish + '</b><small>' + (m.shop || '') + (n.portion ? '・' + n.portion : '') + '</small></td>' +
        '<td>' + (n.kcal || '—') + '</td><td>' + (n.protein_g || '—') + '</td><td>' + (n.na_mg || '—') + '</td>' +
        '<td>' + (n.k_mg || '—') + '</td><td class="hide-m">' + (n.phos_mg || '—') + '</td>' +
        '<td style="text-align:right"><a href="' + (m.url || '#') + '">看店家</a> ' +
        '<button class="linkbtn" data-delmenu="' + m.key + '">移除</button></td></tr>';
    }).join('');

    box.innerHTML = !menu.length
      ? '<div class="empty">本日菜單還是空的。到任何一家店的頁面，在想吃的料理旁按「＋ 加入本日菜單」，這裡就會幫你加總。</div>'
      : '<table class="bibtable plan-table"><thead><tr><th>料理</th><th>熱量<small>kcal</small></th><th>蛋白質<small>g</small></th><th>鈉<small>mg</small></th><th>鉀<small>mg</small></th><th class="hide-m">磷<small>mg</small></th><th></th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
        '<tfoot><tr><th>合計 ' + menu.length + ' 道</th><th>' + Math.round(t.kcal) + '</th><th>' + Math.round(t.protein) + '</th><th>' + Math.round(t.na) + '</th><th>' + Math.round(t.k) + '</th><th class="hide-m">' + Math.round(t.phos) + '</th><th></th></tr></tfoot></table>' +
        '<div class="npanel">' +
          '<h3>對照 ' + ref.label + ' 的一日參考量</h3>' +
          bar('熱量', t.kcal, kc[1], 'kcal') +
          bar('蛋白質', t.protein, pr[1], 'g') +
          bar('鈉', t.na, ref.na, 'mg') +
          (prof.mode === 'normal' ? '' : bar('鉀', t.k, ref.k, 'mg') + bar('磷', t.phos, ref.phos, 'mg')) +
        '</div>' +
        '<div class="advice">' + advise(t, ref, w).map(function (a) {
          return '<p class="a-' + a[0] + '">' + a[1] + '</p>';
        }).join('') + '<p class="fine">' + ref.note + '</p></div>';
  }

  var modeSel = document.getElementById('pmode'), wIn = document.getElementById('pweight');
  if (modeSel) {
    modeSel.value = prof.mode; wIn.value = prof.weight;
    modeSel.onchange = wIn.oninput = function () {
      prof = { mode: modeSel.value, weight: +wIn.value || 60 };
      S.set(PROFILE, prof); render();
    };
    var clr = document.getElementById('pclear');
    if (clr) clr.onclick = function () { menu = []; S.set(KEY, menu); paintButtons(); render(); };
  }
  paintButtons();
  render();
})();
