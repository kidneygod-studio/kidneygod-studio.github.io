// 台南美食通 service worker：網站殼層離線可用，資料採網路優先。
const CACHE = 'tnf-v3';   // 改版就換號，activate 時舊的整批刪掉
// 靜態站：每頁各自是一個 HTML，這裡只預抓首頁與共用資源，其餘瀏覽到才進快取
const SHELL = ['./', './assets/style.css', './assets/app.js', './manifest.webmanifest', './icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const sameOrigin = new URL(req.url).origin === location.origin;
  if (sameOrigin) {
    // 網路優先，離線時退回快取
    // cache:'no-cache' 是必要的：預設的 fetch 仍會走瀏覽器自己的 HTTP 快取，
    // 而 GitHub Pages 送 Cache-Control: max-age=600，所以「網路優先」在十分鐘內
    // 其實拿到的是舊 HTML，還會把舊的再存回 SW 快取（等於舊版被延長保存）。
    // 改成強制向伺服器驗證；內容沒變時伺服器回 304，成本很低。
    e.respondWith(fetch(req, {cache: 'no-cache'}).then(res => {
      const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); return res;
    }).catch(() => caches.match(req).then(r => r || caches.match('./'))));
  } else if (/upload\.wikimedia\.org|fonts\.(googleapis|gstatic)\.com|cdnjs\.cloudflare\.com/.test(req.url)) {
    // 圖片、字型、函式庫：快取優先
    e.respondWith(caches.match(req).then(r => r || fetch(req).then(res => {
      const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); return res;
    })));
  }
});
