/* ═══════════ 雲端進度同步（Firebase）═══════════
   商城與遊戲場共用。設定為 null 時整段休眠，網站功能不受影響。 */
/* ═══════════ 雲端進度同步（Firebase）═══════════
   啟用方式：把下面的 null 換成 Firebase console > 專案設定 > 一般 >
   「你的應用程式」SDK 設定物件（apiKey 等為公開識別碼，可放前端）。
   未填入時本區塊自動休眠，網站功能不受影響。 */
const FIREBASE_CONFIG = {
  apiKey: "AIzaSyCbwPTuDOYdE1TjTd7pzLI6GUXCOPpgJNU",
  authDomain: "kidneygod-ea61e.firebaseapp.com",
  projectId: "kidneygod-ea61e",
  storageBucket: "kidneygod-ea61e.firebasestorage.app",
  messagingSenderId: "494753459903",
  appId: "1:494753459903:web:281898dfc087dad416600a",
};

if (FIREBASE_CONFIG) {
  const { initializeApp } = await import("https://www.gstatic.com/firebasejs/11.0.1/firebase-app.js");
  const { getAuth, onAuthStateChanged, signInAnonymously, GoogleAuthProvider,
          signInWithPopup, linkWithPopup, signOut } =
    await import("https://www.gstatic.com/firebasejs/11.0.1/firebase-auth.js");
  const { getFirestore, doc, getDoc, setDoc, deleteDoc, collection,
          getDocs, getCountFromServer, query, where, orderBy, limit, increment,
          serverTimestamp } =
    await import("https://www.gstatic.com/firebasejs/11.0.1/firebase-firestore.js");

  const app  = initializeApp(FIREBASE_CONFIG);
  const auth = getAuth(app);
  const db   = getFirestore(app);
  const provider = new GoogleAuthProvider();
  let user = null;

  const userDoc = () => doc(db, "users", user.uid);

  async function pull(){
    try{
      const snap = await getDoc(userDoc());
      const cloudState = snap.exists() ? snap.data() : {};
      const merged = mergeState(cloudState, getLocalState());
      applyState(merged);
      await setDoc(userDoc(), {...merged, updatedAt: Date.now()});
      toast("☁️ 進度已同步");
    }catch(e){ console.error("sync pull failed", e); toast("⚠️ 同步失敗，稍後再試"); }
  }

  window.cloud = {
    async push(){
      if(!user) return;
      try{ await setDoc(userDoc(), {...getLocalState(), updatedAt: Date.now()}); }
      catch(e){ console.error("sync push failed", e); }
    },
    renderAccount(){
      const box = document.getElementById("accActions");
      const st  = document.getElementById("accStatus");
      const btn = (label, fn, alt) =>
        `<button class="cta${alt?" alt":""}" style="margin-bottom:8px" data-act="${fn}">${label}</button>`;
      if(!user){
        st.textContent = "未登入 — 進度目前只存在這台裝置的瀏覽器裡";
        box.innerHTML = btn("使用 Google 登入", "google", true) + btn("先匿名開始（不留任何資料）", "anon");
      }else if(user.isAnonymous){
        st.textContent = "匿名同步中 — 識別碼 " + user.uid.slice(0,8) + "…（僅限此瀏覽器）";
        box.innerHTML = btn("升級成 Google 帳號（進度可跨裝置）", "link", true) +
                        btn("登出", "logout") + btn("刪除雲端資料", "wipe");
      }else{
        st.textContent = "已登入：" + (user.email || user.displayName || "Google 帳號");
        box.innerHTML = btn("登出", "logout") + btn("刪除雲端資料", "wipe");
      }
      box.querySelectorAll("button").forEach(b=>{
        b.onclick = () => window.cloud[b.dataset.act]();
      });
    },
    async google(){
      try{ await signInWithPopup(auth, provider); closeAll(); }
      catch(e){ console.error(e); toast("⚠️ Google 登入未完成"); }
    },
    async anon(){
      try{ await signInAnonymously(auth); closeAll(); }
      catch(e){ console.error(e); toast("⚠️ 匿名登入未完成"); }
    },
    async link(){
      try{ await linkWithPopup(auth.currentUser, provider); toast("✅ 已升級為 Google 帳號"); this.renderAccount(); }
      catch(e){ console.error(e); toast("⚠️ 升級未完成（此 Google 帳號可能已有資料）"); }
    },
    async logout(){ await signOut(auth); closeAll(); toast("已登出，進度保留在本機"); },
    async wipe(){
      if(!user) return;
      try{
        await deleteDoc(userDoc());
        /* 自己在各週的成績一併下架（可能從未上榜，失敗不影響刪除流程） */
        try{
          const mine = await getDocs(query(collection(db, "leaderboard"),
                                           where("uid", "==", auth.currentUser.uid)));
          await Promise.all(mine.docs.map(d => deleteDoc(d.ref).catch(()=>{})));
        }catch(e){}
        const u = auth.currentUser;
        await signOut(auth);
        try{ await u.delete(); }catch(e){ /* 需重新驗證時僅刪文件 */ }
        closeAll(); toast("☁️ 雲端資料已刪除，本機進度保留");
      }catch(e){ console.error(e); toast("⚠️ 刪除失敗，稍後再試"); }
    },
  };

  /* ── 站台統計與排行榜（公開讀取）── */
  const statsDoc = () => doc(db, "stats", "site");

  /* 讀取快取。免費方案每天 5 萬次讀取，而一次遊戲場的來回（每輪結算查榜、
     開排行榜面板、上週前三名）本來會重覆查同一份榜單好幾次。榜單變動不快，
     短時間內重查沒有意義，快取起來可以把尖峰時的讀取量壓下一個數量級。 */
  const TOP_TTL = 90e3, CNT_TTL = 300e3;
  function cGet(key, ttl){
    try{
      const o = JSON.parse(sessionStorage[key] || "null");
      return o && Date.now() - o.t < ttl ? o.v : null;
    }catch(e){ return null; }
  }
  function cPut(key, v){
    try{ sessionStorage[key] = JSON.stringify({t: Date.now(), v}); }catch(e){}
  }
  /* 自己送出成績之後榜單就變了，把這一週的快取全部作廢 */
  function cDropWeek(week){
    for(const k of Object.keys(sessionStorage))
      if(k.startsWith("kg_top_" + week)) delete sessionStorage[k];
  }

  window.site = {
    /* 自己的 uid；算名次時要排除自己的舊紀錄，否則會被自己擠掉一名 */
    myId(){ return auth.currentUser ? auth.currentUser.uid : null; },
    /* 目前 Google 登入的信箱（匿名或未登入時為空字串）。
       站長後門用它認人 —— 認的是帳號，不是代碼，代碼被看到也沒用。 */
    myEmail(){
      const u = auth.currentUser;
      return u && !u.isAnonymous && u.email ? u.email.trim().toLowerCase() : "";
    },
    /* 每個瀏覽階段只計一次，避免重整灌水也節省寫入配額 */
    async bumpViews(){
      try{
        if(!sessionStorage.kg_counted){
          sessionStorage.kg_counted = "1";
          await setDoc(statsDoc(), {views: increment(1)}, {merge: true});
        }
        return await this.getViews();
      }catch(e){ console.debug("views bump", e); return null; }
    },
    async getViews(){
      try{
        const snap = await getDoc(statsDoc());
        return snap.exists() ? (snap.data().views || 0) : 0;
      }catch(e){ return null; }
    },
    /* 排行榜每週重來。不刪資料 —— 每筆成績帶著週識別，查詢只取指定的一週，
       上週的紀錄留著給發獎用，但不會再出現在榜上。 */
    async getTop(n = 10, week){
      const wk = week || weekId();
      const key = `kg_top_${wk}_${n}`;
      const hit = cGet(key, TOP_TTL);
      if(hit) return hit;
      try{
        /* 文件 id 是 {uid}_{週次}，同一人同一週只可能有一筆，取 n 筆就夠。
           原本抓 n*5 筆是週制以前用來去重的遺留寫法，等於白花五倍讀取額度。 */
        const q = query(collection(db, "leaderboard"),
                        where("week", "==", wk),
                        orderBy("score", "desc"), limit(n));
        const snap = await getDocs(q);
        const byUser = new Map();
        for(const d of snap.docs){
          const row = {id: d.id, ...d.data()};
          const key = row.uid || d.id;
          const cur = byUser.get(key);
          if(!cur || row.score > cur.score) byUser.set(key, row);
        }
        const rows = [...byUser.values()];
        rows.sort((a, b) =>
          (b.score - a.score) ||
          ((a.at && a.at.seconds || 0) - (b.at && b.at.seconds || 0)));
        const out = rows.slice(0, n);
        cPut(key, out);
        return out;
      }catch(e){ console.debug("leaderboard read", e); return null; }
    },
    /* 本週上榜人數。一人一週一筆，所以文件數就是人數。
       用聚合查詢而不是抓全部文件 —— 每 1000 筆才算一次讀取，不會隨人數變貴。 */
    async playerCount(){
      const key = "kg_cnt_" + weekId();
      const hit = cGet(key, CNT_TTL);
      if(hit !== null) return hit;
      try{
        const q = query(collection(db, "leaderboard"), where("week", "==", weekId()));
        const n = (await getCountFromServer(q)).data().count;
        cPut(key, n);
        return n;
      }catch(e){ console.debug("player count", e); return null; }
    },
    /* 上週前三名，用來發週賽獎金 */
    async lastWeekTop3(){ return this.getTop(3, prevWeekId()); },
    /* 每題的作答統計。記的是「第 N 題被答對了幾次」這種聚合數字，
       不附帶任何身分，也回推不到個人 —— 用途是讓站長知道民眾最常錯哪個觀念。
       一輪十題彙整成一次寫入（不是每題一次），免費方案每天 2 萬次寫入才夠用。
       分散在數份文件是因為單一文件的持續寫入速度約每秒一次，尖峰會塞車。

       ※ 誠實說明：安全規則無法驗證這些數字是不是真的玩出來的，有心人可以灌水。
         這份資料只拿來當選題參考，不適合當成研究數據。 */
    async logQuiz(rows){
      try{
        if(!auth.currentUser || !Array.isArray(rows) || !rows.length) return;
        const q = {};
        for(const r of rows){
          if(!Number.isInteger(r.i) || r.i < 0) continue;
          q[r.i] = {n: increment(1), c: increment(r.ok ? 1 : 0)};
        }
        if(!Object.keys(q).length) return;
        const shard = "s" + Math.floor(Math.random() * 4);
        await setDoc(doc(db, "qstats", shard), {q}, {merge: true});
      }catch(e){ console.debug("qstats write", e); }
    },
    /* 站長儀表板用：把各份統計加總起來 */
    async quizStats(){
      try{
        const snap = await getDocs(collection(db, "qstats"));
        const all = {};
        snap.forEach(d => {
          const q = (d.data() || {}).q || {};
          for(const k of Object.keys(q)){
            const v = q[k] || {};
            all[k] = all[k] || {n: 0, c: 0};
            all[k].n += v.n || 0;
            all[k].c += v.c || 0;
          }
        });
        return all;
      }catch(e){ console.debug("qstats read", e); return null; }
    },
    /* 一人一週一筆，同一週內重複送出就更新那一筆，不會洗版排行榜。 */
    async submitScore(name, score, rounds){
      try{
        if(!auth.currentUser) await signInAnonymously(auth);   // 匿名身分即可，仍不需個資
        const uid = auth.currentUser.uid, week = weekId();
        const clean = String(name || "").trim().slice(0, 16) || "匿名者";
        // 文件 id 帶週次：換週就是新的一筆，不必和上週的分數比大小
        await setDoc(doc(db, "leaderboard", `${uid}_${week}`), {
          uid, week, name: clean,
          score: Math.max(0, Math.min(100, score|0)),
          rounds: Math.max(1, Math.min(10, rounds|0)),
          at: serverTimestamp(),
        });
        cDropWeek(week);          // 榜單已變動，快取作廢
        return clean;
      }catch(e){ console.debug("leaderboard write", e); return null; }
    },
  };

  onAuthStateChanged(auth, u => {
    user = u;
    const label = document.getElementById("loginLabel");
    if(u){ label.textContent = u.isAnonymous ? "匿名同步中" : "已同步"; pull(); }
    else { label.textContent = "登入"; }
  });

  document.getElementById("loginBtn").style.display = "";
}
