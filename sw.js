/* 護腎教室 KidneyGod.Studio — Service Worker
   目的：讓網站能加到手機主畫面、離線也打得開已看過的內容，順便讓回訪變快。

   快取策略照資源性質分開，重點是「絕對不能把使用者卡在舊版」：
     網頁     連線優先，失敗才用快取 —— 內容常改，一定要拿得到新的
     JS／資料 快取優先。網址帶內容雜湊（?v=），改版就是新網址，
              不可能拿到舊的，所以放心直接用快取
     圖片     快取優先（知識卡、貼圖、標誌都很少變動，而且很佔流量）
     其他來源 一律不碰（Firebase、Google 字型等交給瀏覽器自己處理）

   VERSION 由 bump_assets.py 自動更新，改版時舊快取會整批清掉。 */
const VERSION = "kg-e9f27e2087";
const SHELL = `${VERSION}-shell`, IMG = `${VERSION}-img`;

/* 先抓起來的骨架：三個頁面加標誌。JS 與圖片留給實際瀏覽時自然填入，
   不在安裝時一次下載幾百張圖，免得第一次進站就吃掉一堆流量。 */
const PRECACHE = ["./index.html", "./shop.html", "./game.html", "./library.html", "./logo.png"];

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL);
    /* 個別加入：任何一個檔案失敗都不該讓整個安裝失敗 */
    await Promise.all(PRECACHE.map(u => c.add(u).catch(() => {})));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => !k.startsWith(VERSION)).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

const isImg = p => /\.(png|jpe?g|webp|gif|svg|ico)$/i.test(p);
const isAsset = p => /\.(js|css|json|webmanifest)$/i.test(p);

self.addEventListener("fetch", e => {
  const req = e.request;
  if(req.method !== "GET") return;

  const url = new URL(req.url);
  if(url.origin !== self.location.origin) return;      // 外部資源不插手

  /* 網頁：連線優先。拿不到（離線）才退回快取，最後退回商城首頁
     （安裝成 App 的使用者是為了商城與遊戲而來，退回那裡比退回文章首頁有用）。 */
  if(req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html")){
    e.respondWith((async () => {
      try{
        /* cache:"no-cache" 是必要的：預設的 fetch 會走瀏覽器 HTTP 快取，
           而 GitHub Pages 送 max-age=600，所以「連線優先」在十分鐘內
           其實拿到的是舊 HTML，還會把舊的再存回 SW 快取。
           改成強制向伺服器驗證，內容沒變時伺服器回 304，成本很低。 */
        const net = await fetch(req, {cache: "no-cache"});
        const c = await caches.open(SHELL);
        c.put(req, net.clone());
        return net;
      }catch(err){
        return (await caches.match(req, {ignoreSearch: true}))
            || (await caches.match("./shop.html"))
            || (await caches.match("./index.html"))
            || new Response("離線中，且這一頁還沒看過。", {
                 status: 503, headers: {"Content-Type": "text/plain; charset=utf-8"}});
      }
    })());
    return;
  }

  /* 圖片與帶版本號的靜態資源：快取優先，沒有才連線並存起來 */
  if(isImg(url.pathname) || isAsset(url.pathname)){
    e.respondWith((async () => {
      const box = isImg(url.pathname) ? IMG : SHELL;
      const hit = await caches.match(req);
      if(hit) return hit;
      try{
        const net = await fetch(req);
        if(net && net.ok && net.type === "basic"){
          const c = await caches.open(box);
          c.put(req, net.clone());
        }
        return net;
      }catch(err){
        /* JS 有可能是舊版網址被清掉了，退一步用忽略查詢字串的比對 */
        return (await caches.match(req, {ignoreSearch: true}))
            || Response.error();
      }
    })());
  }
});
