// 計算機操作回歸：node test_calc.js（先執行 build_site.py）。
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(__dirname + '/calc.html', 'utf8');
const source = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)]
  .map(m => m[1]).find(s => s.includes('function calcInit()'));
assert.ok(source, '必須測試實際產出的計算機程式');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    const classes = new Set();
    elements.set(id, {value: '', innerHTML: '', textContent: '', style: {}, events: {},
      classList: {add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c)},
      addEventListener(name, fn) { (this.events[name] ||= []).push(fn); }});
  }
  return elements.get(id);
}
function fire(id, event) { for (const fn of element(id).events[event] || []) fn({key: ''}); }
vm.runInNewContext(source, {document: {readyState: 'complete', getElementById: element,
  querySelectorAll: () => ['cAge','cScr','cCys','cAcr'].map(element)}});
function baseline() {
  fire('cClear','click');
  Object.entries({cAge:'55',cSex:'m',cScr:'1.2',cRegion:'nonna'}).forEach(([k,v]) => element(k).value=v);
  fire('cRun','click');
  assert.equal(element('cRes').classList.contains('on'), true);
  assert.ok(element('rEgfr').innerHTML.startsWith('71.4'));
}
for (const id of ['cAge','cSex','cScr','cCys','cAcr','cRegion']) {
  baseline(); fire(id, 'input');
  assert.equal(element('cRes').classList.contains('on'), false, id + ' 變更後不可保留舊結果');
  assert.match(element('cErr').textContent, /重新計算/);
}
for (const [id, value] of [['cAge','10'],['cAge',''],['cScr','0'],['cCys','-1'],['cAcr','0'],['cAcr','-1']]) {
  baseline(); element(id).value=value; fire('cRun','click');
  assert.equal(element('cRes').classList.contains('on'), false, id + ' 無效時不可顯示舊結果');
  assert.ok(element('cErr').textContent.length > 0);
}
baseline(); element('cScr').value='2'; element('cAcr').value='120'; fire('cRun','click');
assert.equal(element('cRes').classList.contains('on'),true);
assert.ok(!/NaN|Infinity/.test(element('rKfre').innerHTML));
assert.match(element('rKfre').innerHTML, /%/);
fire('cClear','click'); assert.equal(element('cRes').classList.contains('on'),false);
console.log('計算機回歸通過：六個欄位變更、六種無效輸入、正常計算、風險顯示與清除。');
