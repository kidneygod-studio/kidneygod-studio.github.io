#!/usr/bin/env python3
"""郭綜合醫院血液透析中心 — 網站產生器（kidneygod.net/dialysis/）

和 build_site.py 完全分開的第二個站。共用網域、不共用任何東西：
不同的配色、不同的字體、不同的版面語言，兩邊的 CSS 也不互相引用。
放在同一個 repo 只是為了共用 GitHub Pages 的部署，不是為了共用程式碼。

版面語言參考 wecareheart.com 的結構慣例（雙語小標 + 大標、卡片區塊、
捲動淡入、深藍頁尾）。程式與文案全部自己寫——那個站是 WordPress ＋
Elementor 產的，它的 CSS 與文字是人家的，只借「版面怎麼組織」這件事。

    python build_dialysis.py

產出：dialysis/index.html 等五頁 + dialysis/assets/{site.css,site.js}
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "dialysis"
BASE_URL = "https://kidneygod.net/dialysis"
TODAY = "2026-09-05"


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------------------
# 機構事實
#
# 全部集中在這裡，是刻意的：這些是關於一間真實醫療機構的事實，寫錯就是錯誤
# 資訊，不能散在各頁的文案裡讓人一句一句去找。值還沒確認的一律留 TODO(...)，
# 頁面上會渲染成黃底的「待填」標記，一眼看得到還缺什麼。
#
# 確認來源請走院方（公關／醫務行政），不要抄網路上的二手資料。
# ---------------------------------------------------------------------------
class TODO(str):
    """待確認的欄位。渲染成醒目的待填標記，不會安靜地變成空字串。"""


FACTS: dict[str, str] = {
    "center":     "郭綜合醫院血液透析中心",
    "hospital":   "郭綜合醫院",
    "addr":       TODO("院區地址"),
    "tel":        TODO("透析室電話"),
    "tel_note":   TODO("服務時間，例如 週一至週六 07:00–21:00"),
    "shifts":     TODO("透析時段，例如 一三五／二四六，早中晚三班"),
    "beds":       TODO("透析床位數"),
    "machines":   TODO("透析機台數"),
    "staff":      TODO("專責護理人員數"),
    # 洗腎室服務專員的 LINE。給的是「找得到人」的窗口，不是院方的行銷帳號——
    # 這一頁的讀者多半是正在準備透析、或臨時需要安排透析的人。
    "line":       TODO("洗腎室服務專員的 LINE ID 或加好友網址"),
    "booking":    TODO("掛號系統網址"),
    "transit":    TODO("大眾運輸方式"),
    "parking":    TODO("停車資訊"),
}

# 醫師陣容。空的時候頁面顯示待填標記；填了就渲染成一張一張的介紹。
# 分開放而不是塞進 FACTS，是因為它是「一份清單」不是「一個值」——
# 塞成一個字串的話，兩位以上就只能用頓號硬串，排版很難看。
#   ("姓名", "職稱", "專長")
DOCTORS: list[tuple[str, str, str]] = [
    # ("吳政哲", "腎臟科主治醫師", "慢性腎臟病、血液透析、腹膜透析、三高"),
]

# 停診／代診公告。
#
# 這一區原本是寫死的「目前無停診公告」。一個永遠寫著「目前無停診」的公告欄，
# 比沒有公告欄更糟——讀者會相信它，然後白跑一趟。所以改成：
#   有公告 → 條列出來
#   沒公告 → 寫「目前無停診公告」，並附上最後確認日期
#
# NOTICE_CHECKED 要手動改。刻意不用 TODAY 自動帶入：那會變成每次建置
# 都宣稱「今天確認過」，但其實沒有人確認，等於用日期說謊。
NOTICE_CHECKED = "2026-09-05"
NOTICES: list[tuple[str, str]] = [
    # ("2026-10-10（六）國慶連假", "當日停診。二四六的病友改至 10/11 補洗，"
    #  "護理人員會主動聯繫確認時段。"),
]

# Cloudflare Web Analytics。**刻意和 build_site.py 用同一個 token**：
# CF 的統計是按網域算的，兩個站都在 kidneygod.net 底下，同一個 token
# 就會在同一個儀表板裡分路徑呈現，不必也不能另外開一個站點。
# 換 token 的時候兩個檔案都要改。不放 cookie、不收個人識別資料。
ANALYTICS_TOKEN = "e44b1d39221d4a5085336497dbff3ce4"


def fact(key: str) -> str:
    v = FACTS[key]
    if isinstance(v, TODO):
        return f'<span class="todo">待填：{esc(str(v))}</span>'
    return esc(v)


def has(key: str) -> bool:
    return not isinstance(FACTS[key], TODO)


def ready() -> bool:
    """機構事實與醫師陣容是否都填完了。

    決定兩件事：頁面要不要輸出 noindex，以及要不要產生 sitemap。
    綁在一起是刻意的——擋搜尋引擎卻又給它一份網址清單，是自相矛盾的。
    """
    return all(not isinstance(v, TODO) for v in FACTS.values()) and bool(DOCTORS)


# ---------------------------------------------------------------------------
# 樣式
# ---------------------------------------------------------------------------
CSS = """
:root{
  --navy:#1e3a63; --navy-d:#162c4b; --blue:#2e7fb8; --teal:#14807a;
  --mist:#f3f7fa; --ink:#333a44; --mut:#6b7480; --line:#dce5ec;
  --bg:#fff; --maxw:1160px; --pad:24px;
  --serif:"Noto Serif TC",Georgia,"Songti TC",serif;
  --sans:"Noto Sans TC",-apple-system,"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:88px}
body{margin:0;font-family:var(--sans);color:var(--ink);background:var(--bg);
line-height:1.85;font-size:16.5px;-webkit-font-smoothing:antialiased;
/* 不加這一行，iOS Safari 橫向時會自己放大字，版面會跑掉。
   check_site.py 第 5 項會擋，兩個站用同一條規則。 */
-webkit-text-size-adjust:100%;text-size-adjust:100%;
overflow-wrap:break-word}
img{max-width:100%;height:auto;display:block}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 var(--pad)}

/* 待填標記：黃底，掃一眼就知道還缺什麼，上線前不該存在。
   不能寫 white-space:nowrap——待填的字比實際值長得多（「待填：透析時段，
   例如 一三五／二四六，早中晚三班」），不換行會把整頁撐出橫向捲軸，
   而且是在還沒放真資料、最容易被忽略的階段。 */
.todo{background:#fff3c4;color:#7a5b00;border:1px dashed #d9ac2e;
border-radius:4px;padding:0 6px;font-size:.86em;
white-space:normal;overflow-wrap:anywhere}

/* ---- 頁首：固定在最上面，捲動後加陰影 ---- */
.hd{position:fixed;inset:0 0 auto;z-index:60;background:var(--navy);
transition:box-shadow .25s,background .25s}
.hd.stuck{box-shadow:0 2px 18px rgba(15,32,58,.28)}
.hd .wrap{display:flex;align-items:center;gap:18px;height:68px}
.logo{display:flex;align-items:center;gap:10px;color:#fff;font-family:var(--serif);
font-size:19px;font-weight:700;letter-spacing:.02em;white-space:nowrap}
.logo:hover{text-decoration:none;color:#fff}
.logo svg{flex-shrink:0}
.hd nav{margin-left:auto;display:flex;align-items:center;gap:26px}
.hd nav a{color:#dbe6f2;font-size:15px;padding:6px 0;position:relative}
.hd nav a:hover{color:#fff;text-decoration:none}
/* 底線從中間長出來，是這類醫療網站很常見的一個小動作 */
.hd nav a::after{content:"";position:absolute;left:50%;right:50%;bottom:0;height:2px;
background:#7fb6e0;transition:left .22s,right .22s}
.hd nav a:hover::after,.hd nav a[aria-current]::after{left:0;right:0}
.hd nav a[aria-current]{color:#fff}
.cta{background:#fff;color:var(--navy)!important;border-radius:999px;
padding:9px 20px!important;font-weight:700;font-size:14.5px;
transition:transform .18s,box-shadow .18s}
.cta::after{display:none}
.cta:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(0,0,0,.22);
text-decoration:none}
/* 手機：選單收成抽屜 */
.burger{display:none;margin-left:auto;width:44px;height:44px;border:0;padding:0;
background:none;color:#fff;cursor:pointer}
.burger span{display:block;width:22px;height:2px;background:#fff;margin:5px auto;
transition:transform .25s,opacity .2s}
.burger[aria-expanded="true"] span:nth-child(1){transform:translateY(7px) rotate(45deg)}
.burger[aria-expanded="true"] span:nth-child(2){opacity:0}
.burger[aria-expanded="true"] span:nth-child(3){transform:translateY(-7px) rotate(-45deg)}
@media(max-width:920px){
  .burger{display:block}
  .hd nav{position:fixed;inset:68px 0 auto;flex-direction:column;align-items:stretch;
  gap:0;background:var(--navy-d);padding:8px 0 18px;margin:0;
  max-height:0;overflow:hidden;transition:max-height .3s ease}
  .hd nav.open{max-height:70vh;overflow:auto}
  .hd nav a{padding:14px 24px;border-bottom:1px solid rgba(255,255,255,.08)}
  .hd nav a::after{display:none}
  .cta{margin:14px 24px 0;text-align:center}
}

/* ---- 主視覺 ---- */
.hero{position:relative;margin-top:68px;min-height:min(74vh,620px);
display:flex;align-items:center;color:#fff;overflow:hidden;
background:linear-gradient(115deg,#4b7fae 0%,#7fa8c9 42%,#cfe0ec 100%)}
.hero .shot{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.hero::after{content:"";position:absolute;inset:0;
background:linear-gradient(90deg,rgba(20,40,72,.72) 0%,rgba(20,40,72,.34) 55%,rgba(20,40,72,.06) 100%)}
/* width:100% 是必要的：.hero 是 flex 容器，.wrap 當 flex item 時寬度由內容
   決定，不會填滿——標題會縮成 598px 並被 margin:0 auto 推到畫面中間，
   和頁首、頁尾、下面各區塊的左緣差 281px（1280px 下實測）。 */
.hero .wrap{position:relative;z-index:2;width:100%;
padding-top:60px;padding-bottom:60px}
.hero .eyebrow{font-size:13px;letter-spacing:.28em;text-transform:uppercase;
color:#bfd8ec;margin:0 0 14px}
.hero h1{font-family:var(--serif);font-size:clamp(28px,5.2vw,50px);line-height:1.32;
margin:0 0 18px;max-width:16em;text-shadow:0 2px 14px rgba(10,25,48,.35)}
.hero p{max-width:30em;font-size:clamp(15px,1.9vw,18px);color:#e7f0f8;margin:0 0 28px}
.hbtns{display:flex;flex-wrap:wrap;gap:12px}
.btn{display:inline-block;border-radius:999px;padding:13px 30px;font-weight:700;
font-size:15.5px;transition:transform .18s,box-shadow .18s,background .18s}
.btn:hover{transform:translateY(-2px);text-decoration:none}
.btn.solid{background:#fff;color:var(--navy)}
.btn.solid:hover{box-shadow:0 8px 22px rgba(0,0,0,.25)}
.btn.ghost{border:1.5px solid rgba(255,255,255,.75);color:#fff}
.btn.ghost:hover{background:rgba(255,255,255,.14)}

/* ---- 區塊骨架：英文小標在上、中文大標在下 ---- */
/* overflow-x:clip 是給淡入動畫用的安全網：.reveal 的起始狀態帶
   translateX，在動畫播完之前那 30px 會伸到視窗外、產生橫向捲軸
   （393px 手機上實測多出 6px）。用 clip 而不是 hidden：hidden 會
   建立捲動容器，把裡面的 position:sticky 一起弄壞。 */
section{padding:clamp(56px,8vw,96px) 0;overflow-x:clip}
section.tint{background:var(--mist)}
.shead{margin:0 0 clamp(28px,4vw,46px)}
.shead .en{display:block;font-size:12.5px;letter-spacing:.34em;text-transform:uppercase;
color:var(--blue);font-weight:700;margin-bottom:8px}
.shead h2{font-family:var(--serif);font-size:clamp(24px,3.6vw,34px);margin:0;
color:var(--navy);line-height:1.4}
.shead .sub{margin:12px 0 0;color:var(--mut);max-width:44em}
.shead.mid{text-align:center}
.shead.mid .sub{margin-left:auto;margin-right:auto}

/* ---- 關於：左圖右文 ---- */
.split{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr);
gap:clamp(28px,5vw,60px);align-items:center}
@media(max-width:860px){.split{grid-template-columns:1fr}}
/* 4:3 而不是參考站的直式：那邊放的是醫師人像，直式合理；
   這裡放的是透析治療區的空景，橫式才看得出空間感，
   硬裁成直式會把兩側的窗與走道切掉六成。 */
.split .fig{border-radius:14px;overflow:hidden;box-shadow:0 18px 40px rgba(23,48,84,.14);
aspect-ratio:4/3;background:linear-gradient(150deg,#c9dcea,#eaf2f8)}
.split .fig img{width:100%;height:100%;object-fit:cover}
.split h3{font-family:var(--serif);font-size:clamp(20px,2.6vw,26px);color:var(--navy);
margin:0 0 14px;line-height:1.5}
.split p{margin:0 0 16px}
.facts{list-style:none;margin:26px 0 0;padding:0;display:grid;
grid-template-columns:repeat(auto-fit,minmax(min(150px,100%),1fr));gap:14px}
.facts li{background:#fff;border:1px solid var(--line);border-radius:12px;
padding:16px 18px}
section.tint .facts li{background:#fff}
.facts b{display:block;font-family:var(--serif);font-size:23px;color:var(--navy);
line-height:1.3}
.facts span{font-size:13.5px;color:var(--mut)}

/* ---- 卡片格線 ---- */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(250px,100%),1fr));
gap:clamp(18px,2.6vw,26px)}
.card{background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;
display:flex;flex-direction:column;transition:transform .22s,box-shadow .22s}
.card:hover{transform:translateY(-5px);box-shadow:0 16px 34px rgba(23,48,84,.13);
text-decoration:none}
.card .ph{aspect-ratio:4/3;background:linear-gradient(140deg,#dbe8f2,#f0f5f9);
position:relative}
.card .ph img{width:100%;height:100%;object-fit:cover}
.card .bd{padding:20px 22px 24px}
.card h3{font-family:var(--serif);font-size:19px;color:var(--navy);margin:0 0 8px;
line-height:1.5}
.card p{margin:0;color:var(--mut);font-size:15px;line-height:1.8}
.card .more{display:inline-block;margin-top:14px;color:var(--blue);font-size:14.5px;
font-weight:700}

/* ---- 公告條 ---- */
.notice{border-left:5px solid var(--teal);background:#fff;border:1px solid var(--line);
border-left:5px solid var(--teal);border-radius:12px;padding:22px 26px}
.notice h3{margin:0 0 10px;font-family:var(--serif);font-size:19px;color:var(--navy)}
.notice ul{margin:0;padding-left:1.2em;color:var(--mut)}
.notice li+li{margin-top:6px}

/* ---- 流程橫幅 ---- */
.band{position:relative;color:#fff;background:linear-gradient(120deg,#1e3a63,#2e7fb8);
overflow:hidden}
.band .shot{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:.35}
.band::after{content:"";position:absolute;inset:0;background:rgba(20,40,72,.55)}
.band .wrap{position:relative;z-index:2}
.band .shead h2,.band .shead .en{color:#fff}
.band .shead .en{color:#a9cbe8}
.band .shead .sub{color:#d8e6f2}
.steps{list-style:none;margin:0;padding:0;display:grid;
grid-template-columns:repeat(auto-fit,minmax(min(210px,100%),1fr));gap:22px}
.steps li{background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.2);
border-radius:14px;padding:24px 22px;backdrop-filter:blur(2px)}
.steps .n{font-family:var(--serif);font-size:34px;line-height:1;color:#a9cbe8;
display:block;margin-bottom:10px}
.steps h3{margin:0 0 8px;font-size:17.5px;font-family:var(--serif)}
.steps p{margin:0;font-size:14.5px;color:#dbe8f3;line-height:1.8}

/* ---- 常見問題手風琴 ---- */
.faq{border-top:1px solid var(--line)}
.faq details{border-bottom:1px solid var(--line)}
.faq summary{list-style:none;cursor:pointer;padding:20px 44px 20px 0;position:relative;
font-family:var(--serif);font-size:17.5px;color:var(--navy);line-height:1.6}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"";position:absolute;right:12px;top:50%;width:11px;height:11px;
border-right:2px solid var(--blue);border-bottom:2px solid var(--blue);
transform:translateY(-70%) rotate(45deg);transition:transform .25s}
.faq details[open] summary::after{transform:translateY(-30%) rotate(-135deg)}
.faq summary:hover{color:var(--blue)}
.faq .ans{padding:0 0 22px;color:var(--mut);max-width:52em}
.faq .ans p{margin:0 0 12px}
.faq .ans p:last-child{margin:0}

/* ---- 頁尾 ---- */
footer.site{background:var(--navy);color:#c7d6e6;padding:56px 0 30px;font-size:14.5px}
footer.site a{color:#c7d6e6}
footer.site a:hover{color:#fff}
.fgrid{display:grid;grid-template-columns:minmax(0,2fr) repeat(auto-fit,minmax(150px,1fr));
gap:32px}
.fgrid h4{font-family:var(--serif);color:#fff;font-size:16px;margin:0 0 12px}
.fgrid ul{list-style:none;margin:0;padding:0}
.fgrid li+li{margin-top:8px}
.fbrand{font-family:var(--serif);color:#fff;font-size:19px;margin:0 0 10px}
.fnote{margin-top:34px;padding-top:20px;border-top:1px solid rgba(255,255,255,.14);
font-size:13px;color:#93a8bf;line-height:1.9}

/* ---- 浮動預約鈕 ---- */
.float{position:fixed;right:20px;bottom:20px;z-index:55;display:flex;align-items:center;
gap:9px;background:var(--teal);color:#fff!important;border-radius:999px;
padding:14px 22px;font-weight:700;font-size:15px;
box-shadow:0 10px 26px rgba(11,74,70,.35);transition:transform .2s,box-shadow .2s}
.float:hover{transform:translateY(-3px);box-shadow:0 14px 32px rgba(11,74,70,.45);
text-decoration:none}
@media(max-width:520px){.float{right:14px;bottom:14px;padding:13px 18px;font-size:14px}}

/* ---- 捲動淡入 ----
   用 IntersectionObserver 加 .in，不是 CSS animation：只播一次、
   而且沒有 JS 時內容照樣看得到（下面 .no-js 直接把它變成顯示狀態）。 */
.reveal{opacity:0;transform:translateY(26px);
transition:opacity .7s cubic-bezier(.22,.61,.36,1),transform .7s cubic-bezier(.22,.61,.36,1);
transition-delay:var(--d,0s)}
/* 左右進場只在雙欄版面用得上。單欄時圖與文是上下排的，
   還做左右滑動只會讓人覺得畫面在晃。 */
@media(min-width:861px){
  .reveal.left{transform:translateX(-30px)}
  .reveal.right{transform:translateX(30px)}
}
.reveal.in{opacity:1;transform:none}
.no-js .reveal{opacity:1;transform:none}
/* 使用者要求減少動態就全部關掉——這個站的讀者有相當比例是長輩與暈眩病人 */
@media(prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  .reveal{opacity:1;transform:none;transition:none}
  .card:hover,.btn:hover,.cta:hover,.float:hover{transform:none}
}

/* ---- 內頁 ---- */
.page-hero{margin-top:68px;background:linear-gradient(120deg,#1e3a63,#3a6d9e);
color:#fff;padding:clamp(46px,7vw,84px) 0}
.page-hero .en{font-size:12.5px;letter-spacing:.34em;text-transform:uppercase;
color:#a9cbe8;font-weight:700;display:block;margin-bottom:8px}
.page-hero h1{font-family:var(--serif);font-size:clamp(26px,4.4vw,40px);margin:0;
line-height:1.4}
.page-hero p{margin:14px 0 0;color:#d8e6f2;max-width:40em}
.prose{max-width:44em}
.prose h2{font-family:var(--serif);color:var(--navy);font-size:clamp(21px,2.8vw,27px);
margin:44px 0 14px;line-height:1.5}
.prose h3{font-family:var(--serif);color:var(--navy);font-size:19px;margin:28px 0 10px}
.prose p{margin:0 0 16px}
.prose ul,.prose ol{margin:0 0 16px;padding-left:1.4em}
.prose li{margin-bottom:8px}
.prose table{width:100%;border-collapse:collapse;margin:0 0 20px;font-size:15px}
.prose th,.prose td{border:1px solid var(--line);padding:11px 13px;text-align:left;
vertical-align:top}
.prose th{background:var(--mist);color:var(--navy);font-weight:700}
/* 醫師陣容。一位一張，姓名、職稱、專長各自成行——
   多位醫師用頓號串成一段的話，讀者要找「誰看什麼」得整段掃過去。 */
.docs{list-style:none;margin:0 0 20px;padding:0;display:grid;
grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr));gap:14px}
.docs li{border:1px solid var(--line);border-radius:12px;padding:16px 18px;
background:var(--mist)}
.docs b{display:block;font-family:var(--serif);font-size:19px;color:var(--navy)}
.docs .r{display:block;font-size:14px;color:var(--blue);margin-top:2px}
.docs .s{display:block;font-size:14.5px;color:var(--mut);margin-top:6px;
line-height:1.75}
.disc{margin-top:48px;background:var(--mist);border-left:4px solid var(--blue);
border-radius:0 10px 10px 0;padding:18px 22px;font-size:14.5px;color:var(--mut)}
"""

JS = """
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
"""

LOGO_SVG = ('<svg viewBox="0 0 24 24" width="26" height="26" fill="none" '
            'stroke="currentColor" stroke-width="1.7" stroke-linecap="round" '
            'aria-hidden="true">'
            '<path d="M14.2 3.1C9 3.1 5 7.1 5 12.4s4 8.5 9.2 8.5c2.9 0 5-1.5 5-3.5 '
            '0-1.8-1.4-2.7-2.8-3.4-.9-.4-1.5-.8-1.5-1.8s.6-1.4 1.5-1.9c1.4-.7 '
            '2.8-1.6 2.8-3.4 0-2-2.1-3.8-5-3.8Z"/>'
            '<path d="M8.4 9.6h3.2M8 12.4h2.6M8.4 15.2h3.2"/></svg>')

NAV = [
    ("index.html", "首頁"),
    ("about.html", "關於中心"),
    ("services.html", "服務項目"),
    ("education.html", "透析衛教"),
    ("visit.html", "就醫資訊"),
]


def shell(path: str, title: str, desc: str, body: str,
          jsonld: dict | None = None) -> str:
    """五頁共用的骨架。"""
    url = f"{BASE_URL}/{'' if path == 'index.html' else path}"
    nav = "".join(
        f'<a href="{h}"{" aria-current=\"page\"" if h == path else ""}>{esc(t)}</a>'
        for h, t in NAV)
    ld = (f'<script type="application/ld+json">'
          f'{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else "")
    # 標誌：img/logo-white.png 放進去就自動換掉內建的線條 SVG。
    # 頁首與頁尾都是深藍底，所以用白色那版；navy 那版留給 favicon。
    mark = ('<img src="img/logo-white.png" alt="" aria-hidden="true" '
            'width="26" height="26" style="height:26px;width:auto">'
            if (OUT / "img" / "logo-white.png").exists() else LOGO_SVG)
    icon = ('<link rel="icon" href="img/logo.png">'
            if (OUT / "img" / "logo.png").exists() else "")
    # 還有待填欄位就擋搜尋引擎。這是一間真實醫療機構的頁面，
    # 帶著「待填：透析室電話」被索引，比晚一點上線糟糕得多。
    # 全部填完之後這一行會自己消失，不必記得回來改。
    robots = "" if ready() else '<meta name="robots" content="noindex,nofollow">\n'
    cf = (f'\n<script type="module" src="https://static.cloudflareinsights.com/'
          f'beacon.min.js" data-cf-beacon=\'{{"token": "{ANALYTICS_TOKEN}"}}\'>'
          f'</script>' if ANALYTICS_TOKEN else "")
    return f"""<!doctype html>
<html lang="zh-Hant" class="no-js">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{robots}<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(FACTS['center'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE_URL}/img/og.jpg">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@500;700&display=swap">
<link rel="stylesheet" href="assets/site.css?v={ASSET_V}">
{icon}
{ld}
</head>
<body>
<header class="hd">
<div class="wrap">
  <a class="logo" href="index.html">{mark}<span>血液透析中心</span></a>
  <button class="burger" type="button" aria-expanded="false" aria-label="選單">
    <span></span><span></span><span></span></button>
  <nav>{nav}<a class="cta" href="visit.html#booking">預約與諮詢</a></nav>
</div>
</header>

{body}

<footer class="site">
<div class="wrap">
  <div class="fgrid">
    <div>
      <p class="fbrand">{fact('center')}</p>
      <p style="margin:0 0 6px">地址：{fact('addr')}</p>
      <p style="margin:0 0 6px">電話：{fact('tel')}</p>
      <p style="margin:0">服務時間：{fact('tel_note')}</p>
    </div>
    <div><h4>認識我們</h4><ul>
      <li><a href="about.html">關於中心</a></li>
      <li><a href="services.html">服務項目</a></li>
      <li><a href="visit.html">就醫資訊</a></li>
    </ul></div>
    <div><h4>給透析病友</h4><ul>
      <li><a href="education.html">透析衛教</a></li>
      <li><a href="index.html#faq">常見問題</a></li>
      <li><a href="visit.html#booking">預約與諮詢</a></li>
    </ul></div>
  </div>
  <p class="fnote">
  本網站內容為一般醫療與衛教資訊，用於說明本中心提供的服務，
  不針對任何個人提供診斷或治療建議，亦不能取代您與主治醫師的討論。<br>
  © {esc(FACTS['hospital'])}　·　本頁最後更新於 {TODAY}
  </p>
</div>
</footer>

<a class="float" href="visit.html#booking">預約與諮詢</a>
<script src="assets/site.js?v={ASSET_V}"></script>{cf}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# 首頁
# ---------------------------------------------------------------------------
SERVICES = [
    ("血液透析", "svc-hd",
     "每週固定次數、以透析器代替腎臟清除代謝廢物與多餘水分。"
     "全程由專責護理人員操作與監測，醫師定期評估透析效率與整體狀況。"),
    ("血液透析過濾（HDF）", "svc-hdf",
     "在傳統透析之外增加對流清除，對中大分子毒素的清除較好，"
     "部分病人在透析中的血壓穩定度與症狀也較理想。是否適合由醫師評估。"),
    ("血管通路照護", "svc-access",
     "透析能不能順利進行，關鍵在通路。從術前規劃、成熟期追蹤，"
     "到日常的自我檢查與異常處理，都有固定的追蹤流程。"),
    ("營養與生活照護", "svc-care",
     "營養師與護理師會依據抽血結果調整飲食建議，"
     "包含蛋白質、磷鉀鈉與水分控制，以及生活作息與運動的安排。"),
]

COLUMNS = [
    ("透析飲食：先顧蛋白質，再談限制", "col-diet",
     "透析病人最常被交代「這不能吃那不能吃」，但真正影響長期預後的，"
     "是蛋白質有沒有吃夠。"),
    ("兩次透析之間，體重可以增加多少？", "col-fluid",
     "水分控制的目標不是「不要喝水」，而是把增加量控制在乾體重的一定比例內。"),
    ("瘻管每天要摸、要聽：三個自我檢查", "col-fistula",
     "瘻管出問題往往有前兆。學會每天花三十秒檢查，可以早一步發現。"),
    ("洗腎之後還能旅行嗎？", "col-travel",
     "可以。但要提前安排——國內一到兩週、國外一到兩個月，"
     "而準備的時間點決定了你能去哪裡。"),
]

STEPS = [
    ("初次評估", "由腎臟科醫師評估腎功能與整體狀況，說明透析時機與三種替代療法。"),
    ("建立通路", "決定透析方式後安排血管通路手術，廔管需要數週到數月成熟。"),
    ("排定時段", "依生活作息安排固定的透析時段，並完成到院流程說明。"),
    ("長期追蹤", "定期抽血、評估透析效率與併發症，營養與用藥隨結果調整。"),
]

FAQ = [
    ("要開始透析了，是不是代表病情已經很嚴重？",
     ["不完全是。開始透析看的是身體有沒有出現無法代償的症狀與檢驗異常，"
      "而不是單一個數字。同樣的腎功能數值，兩個人的處置可以完全不同。",
      "在還有餘裕的時候開始準備，反而比拖到必須緊急插管才開始，"
      "有更多選擇空間、也更安全。"]),
    ("一週要來幾次？每次多久？",
     ["多數人是每週三次、每次約四小時，時段固定。實際次數與時間由醫師依據"
      "殘餘腎功能、體型與檢驗結果決定，不是每個人都一樣。"]),
    ("透析中會不會不舒服？",
     ["常見的是透析中或結束後的疲倦、抽筋與血壓下降，多半與脫水速度、"
      "兩次之間水分增加太多有關。這些狀況大多可以透過調整處方與水分控制改善，"
      "請主動告訴護理人員，不要忍。"]),
    ("可以繼續工作嗎？",
     ["很多人可以。時段能配合作息是關鍵，也可以和醫師討論腹膜透析等"
      "彈性較高的方式。工作型態、輪班與出差需求，值得在選擇透析方式時就講出來。"]),
    ("飲食是不是什麼都不能吃？",
     ["不是。透析病人反而需要足夠的蛋白質，長期吃太少會造成營養不良，"
      "而營養不良對存活的影響比一次血磷偏高大得多。",
      "需要控制的是磷、鉀、鈉與水分，而不是把食物整類刪掉。"
      "本中心的營養師會依你的抽血結果給具體建議。"]),
    ("需要自費嗎？",
     ["常規血液透析由健保給付。部分特殊材質的透析器、藥品或檢查可能需要自費，"
      "會在使用前說明並徵得同意。若有任何費用疑問，可以直接詢問櫃檯或個管師。"]),
]


def rv(base: str = "", dirn: str = "", delay: float = 0.0) -> str:
    """捲動淡入用的屬性。base 是元素本來就有的 class，一定要從這裡傳進來。

    不要寫成 <div class="card"{rv(...)}>——那會產生兩個 class 屬性，
    瀏覽器只認第一個，元素永遠停在 opacity:0 或永遠不會動，而且不會噴錯。
    （第一版就是這樣寫的，四張服務卡片與四張專欄卡片全部沒有動畫。）
    """
    names = " ".join(x for x in (base, "reveal", dirn) if x)
    d = f' style="--d:{delay:.2f}s"' if delay else ""
    return f' class="{names}"{d}'


def img_or_ph(name: str, alt: str, cls: str = "") -> str:
    """圖還沒進來時留漸層佔位塊——沒有破圖，之後把檔案放進 img/ 就會自己出現。"""
    f = OUT / "img" / f"{name}.jpg"
    if f.exists():
        return (f'<img src="img/{name}.jpg" alt="{esc(alt)}" loading="lazy"'
                f'{f" class={cls}" if cls else ""}>')
    return ""


def build_home() -> str:
    svc = "".join(
        f'<a href="services.html#{slug}"{rv("card", "", i * .08)}>'
        f'<div class="ph">{img_or_ph(slug, name)}</div>'
        f'<div class="bd"><h3>{esc(name)}</h3><p>{esc(text)}</p>'
        f'<span class="more">了解更多 →</span></div></a>'
        for i, (name, slug, text) in enumerate(SERVICES))

    col = "".join(
        f'<a href="education.html#{slug}"{rv("card", "", i * .08)}>'
        f'<div class="ph">{img_or_ph(slug, name)}</div>'
        f'<div class="bd"><h3>{esc(name)}</h3><p>{esc(text)}</p>'
        f'<span class="more">閱讀 →</span></div></a>'
        for i, (name, slug, text) in enumerate(COLUMNS))

    steps = "".join(
        f'<li{rv("", "", i * .1)}><span class="n">{i + 1:02d}</span>'
        f'<h3>{esc(t)}</h3><p>{esc(d)}</p></li>'
        for i, (t, d) in enumerate(STEPS))

    faq = "".join(
        f'<details{rv("", "", min(i, 4) * .05)}><summary>{esc(q)}</summary>'
        f'<div class="ans">{"".join(f"<p>{esc(p)}</p>" for p in a)}</div></details>'
        for i, (q, a) in enumerate(FAQ))

    # 沒有公告時附上最後確認日期。少了這個日期，讀者沒辦法分辨
    # 「今天確認過沒有停診」和「三年前寫上去就沒人管過」。
    if NOTICES:
        notice = ('<h3>近期公告</h3><ul>'
                  + "".join(f'<li><strong>{esc(w)}</strong>：{esc(t)}</li>'
                            for w, t in NOTICES)
                  + '</ul>')
    else:
        notice = (f'<h3>目前無停診公告</h3>'
                  f'<p class="sd" style="margin:0 0 10px">'
                  f'最後確認：{esc(NOTICE_CHECKED)}</p><ul>')
        notice += (
            '<li>國定假日與颱風天的透析安排，會另行公告並由護理人員主動聯繫。</li>'
            f'<li>臨時無法到院透析，請盡早來電，我們會協助安排補洗時段：'
            f'{fact("tel")}</li></ul>')

    hero_img = (f'<img class="shot" src="img/hero.jpg" alt="">'
                if (OUT / "img" / "hero.jpg").exists() else "")
    band_img = (f'<img class="shot" src="img/band-process.jpg" alt="">'
                if (OUT / "img" / "band-process.jpg").exists() else "")
    about_img = img_or_ph("about-center", "本中心的透析治療區")

    body = f"""
<section class="hero">{hero_img}<div class="wrap">
  <p{rv("eyebrow")}>Hemodialysis Center</p>
  <h1{rv("", "", .08)}>把透析放進生活裡，<br>而不是讓生活繞著透析走</h1>
  <p{rv("", "", .16)}>{fact('center')}提供血液透析、血液透析過濾與完整的
  血管通路照護。固定的醫療團隊、固定的時段，讓長期治療能被安排進日常。</p>
  <div{rv("hbtns", "", .24)}>
    <a class="btn solid" href="visit.html#booking">預約與諮詢</a>
    <a class="btn ghost" href="services.html">看服務項目</a>
  </div>
</div></section>

<section class="tint"><div class="wrap">
  <div class="split">
    <div{rv("fig", "left")}>{about_img}</div>
    <div{rv("", "right", .1)}>
      <p class="shead" style="margin-bottom:18px">
        <span class="en">About us</span></p>
      <h3>長期的治療，需要一個穩定的地方</h3>
      <p>血液透析不是一次性的處置，而是每週要回來好幾次、可能持續很多年的事。
      在這樣的前提下，「醫療團隊會不會換」「時段能不能配合生活」
      「有問題找不找得到人」，往往比任何單項設備都更影響治療品質。</p>
      <p>本中心由腎臟科專科醫師與專責透析護理人員組成固定團隊，
      配合營養師與社工，從開始透析前的評估、通路建立，到長期的併發症追蹤，
      在同一個地方完成。</p>
      <a class="btn solid" style="background:var(--navy);color:#fff"
         href="about.html">認識我們的團隊</a>
      <ul class="facts">
        <li><b>{fact('machines')}</b><span>透析機台</span></li>
        <li><b>{fact('shifts')}</b><span>透析時段</span></li>
        <li><b>{fact('staff')}</b><span>專責護理人員</span></li>
      </ul>
    </div>
  </div>
</div></section>

<section><div class="wrap">
  <div class="shead mid reveal">
    <span class="en">Services</span>
    <h2>服務項目</h2>
    <p class="sub">從透析治療本身，到通路、營養與長期併發症的追蹤，
    在同一個團隊裡完成。</p>
  </div>
  <div class="grid">{svc}</div>
</div></section>

<section class="tint"><div class="wrap">
  <div class="shead reveal"><span class="en">Notice</span><h2>停診與代診公告</h2></div>
  <div{rv("notice", "", .08)}>{notice}</div>
</div></section>

<section class="band">{band_img}<div class="wrap">
  <div class="shead mid reveal">
    <span class="en">Process</span>
    <h2>從評估到長期追蹤</h2>
    <p class="sub">第一次來不知道會發生什麼，是很多人最焦慮的部分。
    這是完整的流程。</p>
  </div>
  <ul class="steps">{steps}</ul>
</div></section>

<section><div class="wrap">
  <div class="shead mid reveal">
    <span class="en">Column</span>
    <h2>透析衛教</h2>
    <p class="sub">門診與透析室裡最常被問到的事，寫成看得懂的文章。</p>
  </div>
  <div class="grid">{col}</div>
</div></section>

<section class="tint" id="faq"><div class="wrap">
  <div class="shead mid reveal">
    <span class="en">FAQ</span>
    <h2>常見問題</h2>
  </div>
  <div class="faq" style="max-width:56em;margin:0 auto">{faq}</div>
</div></section>
"""
    ld = {
        "@context": "https://schema.org",
        "@type": "MedicalClinic",
        "name": FACTS["center"],
        "medicalSpecialty": "Nephrologic",
        "url": f"{BASE_URL}/",
        "parentOrganization": {"@type": "Hospital", "name": FACTS["hospital"]},
    }
    if has("addr"):
        ld["address"] = {"@type": "PostalAddress", "streetAddress": FACTS["addr"]}
    if has("tel"):
        ld["telephone"] = FACTS["tel"]
    return shell("index.html",
                 f"{FACTS['center']}｜血液透析、血液透析過濾與血管通路照護",
                 "郭綜合醫院血液透析中心：血液透析、血液透析過濾（HDF）、"
                 "血管通路照護與營養追蹤，由腎臟科專科醫師與專責透析護理團隊提供。",
                 body, ld)


# ---------------------------------------------------------------------------
# 內頁
# ---------------------------------------------------------------------------
def page_hero(en: str, h1: str, lead: str = "") -> str:
    p = f'<p>{lead}</p>' if lead else ""
    return (f'<section class="page-hero"><div class="wrap">'
            f'<span class="en">{esc(en)}</span><h1>{esc(h1)}</h1>{p}'
            f'</div></section>')


def doctors_html() -> str:
    if not DOCTORS:
        return ('<p><span class="todo">待填：醫師陣容——'
                '在 build_dialysis.py 的 DOCTORS 加上（姓名, 職稱, 專長）</span></p>')
    return ('<ul class="docs">'
            + "".join(f'<li><b>{esc(n)}</b><span class="r">{esc(t)}</span>'
                      f'<span class="s">{esc(s)}</span></li>'
                      for n, t, s in DOCTORS)
            + '</ul>')


def build_about() -> str:
    body = page_hero("About us", "關於中心",
                     "長期的治療需要一個穩定的地方——固定的團隊、固定的時段、"
                     "有問題找得到人。") + f"""
<section><div class="wrap"><div class="prose reveal">
<h2>我們是誰</h2>
<p>{fact('center')}由腎臟科專科醫師與專責透析護理人員組成固定團隊，
配合營養師與社工，提供血液透析與血液透析過濾治療。</p>
<h3>醫療團隊</h3>
{doctors_html()}
<h3>設備與規模</h3>
<ul>
  <li>透析機台：{fact('machines')}</li>
  <li>透析床位：{fact('beds')}</li>
  <li>專責護理人員：{fact('staff')}</li>
  <li>透析時段：{fact('shifts')}</li>
</ul>

<h2>我們怎麼照顧一位透析病人</h2>
<p>透析不是把血洗乾淨就結束。真正決定長期生活品質的，是那些不會在
單次治療裡看出來的事：貧血、骨骼與礦物質代謝、營養狀況、血管通路的壽命、
以及心血管風險。</p>
<ul>
  <li><strong>每次透析</strong>：監測血壓與症狀，記錄脫水量與透析中的變化。</li>
  <li><strong>定期抽血</strong>：評估透析效率、貧血、電解質與營養指標，
  據以調整處方與用藥。</li>
  <li><strong>通路追蹤</strong>：定期評估血流與再循環，早期發現狹窄。</li>
  <li><strong>營養評估</strong>：依抽血結果調整飲食建議，重點是吃得夠，
  不是吃得少。</li>
</ul>

<h2>關於這個網站</h2>
<p>這裡的內容是為了讓即將開始透析、或已經在透析的人，
以及他們的家人，知道會發生什麼事、可以問什麼問題。
所有醫療內容依據現行指引撰寫並定期檢視。</p>
<div class="disc">本網站內容為一般醫療與衛教資訊，不針對任何個人提供診斷或治療建議。
您的實際處置請以主治醫師的評估為準。</div>
</div></div></section>
"""
    return shell("about.html", f"關於中心｜{FACTS['center']}",
                 "郭綜合醫院血液透析中心的醫療團隊、設備規模，"
                 "以及長期透析照護的追蹤方式。", body)


def build_services() -> str:
    blocks = []
    detail = {
        "svc-hd": [
            "<h3>治療方式</h3>",
            "<p>把血液引出體外，經過透析器（人工腎臟）清除代謝廢物與多餘水分，"
            "再回到體內。多數人每週三次、每次約四小時，實際處方由醫師依據"
            "殘餘腎功能、體型與檢驗結果決定。</p>",
            "<h3>過程中會監測什麼</h3>",
            "<ul><li>血壓與心跳，特別是脫水速度較快的時段</li>"
            "<li>透析中的症狀：抽筋、噁心、頭暈、胸悶</li>"
            "<li>脫水量是否達到目標，以及乾體重是否需要調整</li></ul>",
        ],
        "svc-hdf": [
            "<h3>和一般血液透析的差別</h3>",
            "<p>在擴散清除之外增加對流清除，對中大分子毒素的清除較好。"
            "部分病人在透析中的血壓穩定度與症狀較理想。</p>",
            "<h3>誰適合</h3>",
            "<p>需要足夠的血流量與良好的通路條件，並非每個人都適合，"
            "由醫師評估後決定。</p>",
        ],
        "svc-access": [
            "<h3>三種通路</h3>",
            "<table><tr><th>類型</th><th>需要多久</th><th>特點</th></tr>"
            "<tr><td>自體動靜脈廔管</td><td>手術後數週至數月成熟</td>"
            "<td>感染率最低、使用年限最長，是首選</td></tr>"
            "<tr><td>人工血管</td><td>手術後數週</td>"
            "<td>血管條件不佳時的選擇，較易狹窄與血栓</td></tr>"
            "<tr><td>中心靜脈洗腎導管</td><td>可立即使用</td>"
            "<td>感染與血栓風險最高，原則上是過渡方案</td></tr></table>",
            "<h3>每天要做的自我檢查</h3>",
            "<ul><li><strong>摸</strong>：有沒有震顫（thrill）</li>"
            "<li><strong>聽</strong>：有沒有連續的雜音（bruit）</li>"
            "<li><strong>看</strong>：有沒有紅、腫、熱、痛或滲液</li></ul>",
            "<p>震顫變弱或消失、出現搏動感，請立刻聯絡透析室，不要等到下次透析。</p>",
        ],
        "svc-care": [
            "<h3>營養</h3>",
            "<p>透析病人需要比一般人更多的蛋白質。長期吃太少造成的營養不良，"
            "對存活的影響比偶爾一次血磷偏高大得多。營養師會依你的抽血結果"
            "給具體、可執行的建議，而不是一張「不能吃」的清單。</p>",
            "<h3>水分</h3>",
            "<p>兩次透析之間的體重增加，一般建議控制在乾體重的 3–5% 以內。"
            "增加太多會讓單次要脫的水變多，透析中的血壓波動與抽筋也跟著變多。</p>",
            "<h3>運動</h3>",
            "<p>可以，而且應該。規律的中等強度運動對體能、睡眠與情緒都有幫助。"
            "有廔管的那隻手避免提重物與壓迫，其餘活動多半不受限制。</p>",
        ],
    }
    for i, (name, slug, lead) in enumerate(SERVICES):
        blocks.append(
            f'<section{" class=\"tint\"" if i % 2 else ""} id="{slug}">'
            f'<div class="wrap"><div class="prose reveal">'
            f'<h2 style="margin-top:0">{esc(name)}</h2>'
            f'<p>{esc(lead)}</p>'
            + "".join(detail.get(slug, []))
            + '</div></div></section>')
    body = (page_hero("Services", "服務項目",
                      "從透析治療本身，到通路、營養與長期併發症的追蹤。")
            + "".join(blocks))
    return shell("services.html", f"服務項目｜{FACTS['center']}",
                 "血液透析、血液透析過濾（HDF）、血管通路照護與營養生活照護，"
                 "各項服務的內容與追蹤方式。", body)


def build_education() -> str:
    arts = {
        "col-diet": [
            "<p>透析病人最常被交代的是「這不能吃、那不能吃」，"
            "但門診裡真正常見的問題，其實是吃得不夠。</p>",
            "<h3>蛋白質要吃夠</h3>",
            "<p>透析過程本身會流失胺基酸，所以透析病人需要的蛋白質比一般人多。"
            "長期攝取不足會造成肌肉流失與營養不良，而營養不良對長期存活的影響，"
            "比偶爾一次血磷偏高大得多。</p>",
            "<h3>磷的重點不是總量，是來源</h3>",
            "<p>加工食品裡的無機磷吸收率接近百分之百，天然食物裡的有機磷"
            "吸收率低得多。同樣的磷含量，來源不一樣，對身體的影響差很多。"
            "先減少加工食品，通常比刻意少吃蛋白質更有效。</p>",
            "<h3>鉀</h3>",
            "<p>需要控制，但不必把所有蔬果都排除。烹調方式（先汆燙再炒）"
            "可以有效降低鉀含量。實際的限制範圍請依你的抽血結果，"
            "由營養師個別建議。</p>",
        ],
        "col-fluid": [
            "<p>水分控制的目標不是「不要喝水」，而是把兩次透析之間的體重增加"
            "控制在合理範圍——一般建議是乾體重的 3–5% 以內。</p>",
            "<h3>為什麼要控制</h3>",
            "<p>兩次之間增加太多，單次要脫的水就變多，脫水速度變快，"
            "透析中的低血壓、抽筋與不適也跟著變多。長期的水分過多還會造成"
            "高血壓與心臟負擔。</p>",
            "<h3>比較實際的做法</h3>",
            "<ul><li>控制鹽分。鹽吃多了會口渴，限水就會很痛苦——先減鹽比先限水有效。</li>"
            "<li>用固定容量的杯子，把一天的量倒出來，喝完就沒有了。</li>"
            "<li>口乾時用冰塊或漱口，比直接喝一杯水有效。</li>"
            "<li>每天固定時間、同樣的衣著量體重，數字才有比較的意義。</li></ul>",
        ],
        "col-fistula": [
            "<p>瘻管出問題通常有前兆。每天花三十秒檢查，可以在還來得及處理的"
            "時候發現它。</p>",
            "<h3>摸、聽、看</h3>",
            "<ul><li><strong>摸</strong>：把手指輕放在瘻管上，"
            "應該摸得到持續的震顫，像小貓打呼。</li>"
            "<li><strong>聽</strong>：貼著聽，應該是連續的「呼——」聲，"
            "不是一跳一跳的。</li>"
            "<li><strong>看</strong>：有沒有紅腫、發熱、疼痛、滲液，"
            "或是手部腫脹、發麻、冰冷。</li></ul>",
            "<h3>這些情況要立刻聯絡</h3>",
            "<ul><li>震顫變弱或摸不到</li><li>聲音從連續變成一跳一跳</li>"
            "<li>局部紅腫熱痛，或有分泌物</li>"
            "<li>止血時間明顯變長</li></ul>",
            "<h3>日常要避免的事</h3>",
            "<p>有瘻管的那隻手不量血壓、不抽血、不打點滴，"
            "不提重物、不戴太緊的手錶或袖口，睡覺時不要壓著。</p>",
        ],
        "col-travel": [
            "<p>透析病人可以旅行，但要提前安排。國內建議提前一到兩週，"
            "國外一到兩個月——而準備的時間點，實際上決定了你能去哪裡。</p>",
            "<h3>血液透析</h3>",
            "<p>要先找到目的地的合作透析院所並預約時段，"
            "帶著病歷摘要、近期抽血報告與透析處方。"
            "國內可申請健保核退，需要的文件請提前向透析室確認。</p>",
            "<h3>腹膜透析</h3>",
            "<p>機動性較高，但透析液的配送要提前安排；出國需要中英文診斷書，"
            "建議提前約三個月準備。</p>",
            "<h3>什麼時候不適合出發</h3>",
            "<p>剛開始透析、還在調整乾體重，或近期有感染、心衰竭、"
            "通路狀況不穩定時，先把狀況穩下來再安排。"
            "行前請務必和你的主治醫師討論。</p>",
        ],
    }
    blocks = []
    for i, (name, slug, lead) in enumerate(COLUMNS):
        blocks.append(
            f'<section{" class=\"tint\"" if i % 2 else ""} id="{slug}">'
            f'<div class="wrap"><div class="prose reveal">'
            f'<h2 style="margin-top:0">{esc(name)}</h2>'
            + "".join(arts.get(slug, [f"<p>{esc(lead)}</p>"]))
            + '</div></div></section>')
    body = (page_hero("Column", "透析衛教",
                      "門診與透析室裡最常被問到的事，寫成看得懂的文章。")
            + "".join(blocks)
            + '<section><div class="wrap"><div class="disc" style="margin:0">'
              '以上內容為一般衛教資訊，實際的飲食限制、水分目標與用藥，'
              '請依你的抽血結果與主治醫師的評估為準。</div></div></section>')
    return shell("education.html", f"透析衛教｜{FACTS['center']}",
                 "透析飲食、水分控制、瘻管自我照護與旅遊透析——"
                 "透析室裡最常被問到的四件事。", body)


def build_visit() -> str:
    body = page_hero("Visit", "就醫資訊", "怎麼來、怎麼預約、第一次來要帶什麼。") + f"""
<section id="booking"><div class="wrap"><div class="prose reveal">
<h2 style="margin-top:0">預約與諮詢</h2>
<p>不論是想先了解透析、需要安排長期時段，或是外地就醫需要臨時透析，
都可以直接聯絡我們。</p>
<ul>
  <li><strong>電話</strong>：{fact('tel')}（{fact('tel_note')}）</li>
  <li><strong>地址</strong>：{fact('addr')}</li>
  <li><strong>線上掛號</strong>：{fact('booking')}</li>
  <li><strong>洗腎室服務專員 LINE</strong>：{fact('line')}</li>
</ul>

<h2>第一次來，請帶這些</h2>
<ul>
  <li>健保卡與身分證件</li>
  <li>近期的抽血與檢查報告（如果有）</li>
  <li>目前正在服用的所有藥物，或藥袋、藥單</li>
  <li>其他院所的病歷摘要（如果是轉診或臨時透析）</li>
</ul>

<h2>透析時段</h2>
<p>{fact('shifts')}</p>
<p>時段一旦排定就固定下來，方便安排工作與生活。
臨時無法到院請盡早來電，我們會協助安排補洗。</p>

<h2>臨時透析與旅遊透析</h2>
<p>短期停留台南、需要安排臨時透析的病友，請提前來電，
並準備病歷摘要、近期抽血報告與透析處方。詳細的準備事項可以參考
<a href="education.html#col-travel">旅遊透析那一篇</a>。</p>

<h2>交通</h2>
<ul>
  <li><strong>大眾運輸</strong>：{fact('transit')}</li>
  <li><strong>停車</strong>：{fact('parking')}</li>
</ul>

<div class="disc">若您出現喘不過氣、胸悶、意識改變、
瘻管處大量出血或劇烈疼痛等狀況，請直接就醫或撥打 119，不要等到下次透析。</div>
</div></div></section>
"""
    return shell("visit.html", f"就醫資訊｜{FACTS['center']}",
                 "郭綜合醫院血液透析中心的預約方式、透析時段、"
                 "第一次就診要準備的東西與交通資訊。", body)


# ---------------------------------------------------------------------------
ASSET_V = "1"


def main() -> None:
    global ASSET_V
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    (OUT / "img_src").mkdir(parents=True, exist_ok=True)

    css = re.sub(r"\n{3,}", "\n\n", CSS).strip() + "\n"
    js = JS.strip() + "\n"
    (OUT / "assets" / "site.css").write_text(css, encoding="utf-8")
    (OUT / "assets" / "site.js").write_text(js, encoding="utf-8")

    # 版本號＝兩個檔案的雜湊。服務工作者對 .css/.js 是快取優先，
    # 沒有這個查詢字串，改了樣式的人永遠看到舊版。
    import hashlib
    ASSET_V = hashlib.sha1((css + js).encode("utf-8")).hexdigest()[:8]

    pages = {
        "index.html": build_home(),
        "about.html": build_about(),
        "services.html": build_services(),
        "education.html": build_education(),
        "visit.html": build_visit(),
    }
    for name, html_text in pages.items():
        (OUT / name).write_text(html_text, encoding="utf-8")
        print(f"  dialysis/{name}　({len(html_text):,} bytes)")
    print(f"  dialysis/assets/site.css　({len(css):,} bytes)")
    print(f"  dialysis/assets/site.js　({len(js):,} bytes)　v={ASSET_V}")

    # sitemap 和 noindex 綁在同一個條件：擋著搜尋引擎卻又遞給它一份網址清單，
    # 是自相矛盾的。還沒 ready 就把舊的 sitemap 刪掉，不留下會誤導的殘檔。
    sm = OUT / "sitemap.xml"
    if ready():
        urls = "".join(
            f"<url><loc>{BASE_URL}/{'' if n == 'index.html' else n}</loc>"
            f"<lastmod>{TODAY}</lastmod><changefreq>monthly</changefreq>"
            f"<priority>{'1.0' if n == 'index.html' else '0.8'}</priority></url>"
            for n in pages)
        sm.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                      f"{urls}</urlset>\n", encoding="utf-8")
        print(f"  dialysis/sitemap.xml　({len(pages)} 個網址)")
    elif sm.exists():
        sm.unlink()

    todo = [k for k, v in FACTS.items() if isinstance(v, TODO)]
    have = len(FACTS) - len(todo)
    print(f"\n機構事實：{have}/{len(FACTS)} 已填")
    if todo:
        print("  還缺（填在 build_dialysis.py 最上面的 FACTS）：")
        for k in todo:
            print(f"    {k:<10}{FACTS[k]}")
    if not DOCTORS:
        print("  還缺　DOCTORS　醫師陣容（姓名, 職稱, 專長）")
    if NOTICES:
        print(f"\n停診公告：{len(NOTICES)} 則")
    else:
        print(f"\n停診公告：無，頁面顯示「最後確認：{NOTICE_CHECKED}」"
              f"（確認過記得改 NOTICE_CHECKED）")

    missing = [n for _t, n, _d in SERVICES + COLUMNS] + ["hero", "about-center",
                                                         "band-process"]
    absent = [n for n in missing if not (OUT / "img" / f"{n}.jpg").exists()]
    print(f"\n圖片：{len(missing) - len(absent)}/{len(missing)} 已放"
          + (f"（缺 {', '.join(absent)}）" if absent else ""))

    print(f"\n可以上線了嗎：{'✓ 是，已產生 sitemap、已移除 noindex' if ready() else '✗ 還沒，五頁維持 noindex、不產生 sitemap'}")
    if ready():
        print("  記得到 Search Console 提交 "
              f"{BASE_URL}/sitemap.xml（和主站的是兩份）")


if __name__ == "__main__":
    main()
