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
      try{
        const q = query(collection(db, "leaderboard"),
                        where("week", "==", week || weekId()),
                        orderBy("score", "desc"), limit(n * 5));
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
        return rows.slice(0, n);
      }catch(e){ console.debug("leaderboard read", e); return null; }
    },
    /* 本週上榜人數。一人一週一筆，所以文件數就是人數。
       用聚合查詢而不是抓全部文件 —— 每 1000 筆才算一次讀取，不會隨人數變貴。 */
    async playerCount(){
      try{
        const q = query(collection(db, "leaderboard"), where("week", "==", weekId()));
        return (await getCountFromServer(q)).data().count;
      }catch(e){ console.debug("player count", e); return null; }
    },
    /* 上週前三名，用來發週賽獎金 */
    async lastWeekTop3(){ return this.getTop(3, prevWeekId()); },
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
