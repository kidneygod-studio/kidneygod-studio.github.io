document.documentElement.classList.remove('no-js');

/* 頁首捲動後加陰影 */
(function(){
  var hd = document.querySelector('.hd');
  if(!hd) return;
  var on = false;
  addEventListener('scroll', function(){
    var want = scrollY > 8;
    if(want !== on){ on = want; hd.classList.toggle('stuck', on); }
  }, {passive:true});
})();

/* 手機選單 */
(function(){
  var b = document.querySelector('.burger'), nav = document.querySelector('.hd nav');
  if(!b || !nav) return;
  b.addEventListener('click', function(){
    var open = b.getAttribute('aria-expanded') === 'true';
    b.setAttribute('aria-expanded', String(!open));
    nav.classList.toggle('open', !open);
  });
  /* 點了連結就收起來，不然跳到錨點之後選單還蓋在上面 */
  nav.addEventListener('click', function(e){
    if(e.target.closest('a')){
      b.setAttribute('aria-expanded','false');
      nav.classList.remove('open');
    }
  });
})();

/* 捲動淡入。只播一次——重複播放在長頁面上會讓人暈。
 *
 * 刻意不用 IntersectionObserver：整個版面靠 .reveal 的 opacity:0 起始，
 * 只要觀察器因為任何理由沒回呼，整頁就是全白。實測在內嵌式的預覽視窗裡
 * 它一次都沒觸發過。自己量 getBoundingClientRect 沒有這個風險，
 * 元素數量只有三十個，rAF 節流之後成本可以忽略。
 * 最後再加一道三秒保險：動畫沒播只是可惜，內容看不到是災難。 */
(function(){
  var els = [].slice.call(document.querySelectorAll('.reveal'));
  if(!els.length) return;

  function showAll(){
    els.forEach(function(el){ el.classList.add('in'); });
    els = [];
    teardown();
  }
  function teardown(){
    removeEventListener('scroll', onScroll);
    removeEventListener('resize', onScroll);
  }
  if(matchMedia('(prefers-reduced-motion: reduce)').matches){ showAll(); return; }

  var ticking = false;
  function check(){
    ticking = false;
    /* 進到畫面下緣往上 12% 才播，和捲動的節奏比較合；
       已經捲過去的元素 top 也小於這條線，所以往回捲不會看到空白。 */
    var line = (innerHeight || document.documentElement.clientHeight) * 0.88;
    var left = [];
    for(var i = 0; i < els.length; i++){
      if(els[i].getBoundingClientRect().top < line) els[i].classList.add('in');
      else left.push(els[i]);
    }
    els = left;
    if(!els.length) teardown();
  }
  function onScroll(){
    if(!ticking){ ticking = true; requestAnimationFrame(check); }
  }
  addEventListener('scroll', onScroll, {passive:true});
  addEventListener('resize', onScroll);
  check();
  addEventListener('load', check);
  setTimeout(showAll, 3000);
})();

/* 手風琴一次只開一個 */
(function(){
  var box = document.querySelector('.faq');
  if(!box) return;
  var all = box.querySelectorAll('details');
  all.forEach(function(d){
    d.addEventListener('toggle', function(){
      if(!d.open) return;
      all.forEach(function(o){ if(o !== d) o.open = false; });
    });
  });
})();
