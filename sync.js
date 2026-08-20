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
          addDoc, getDocs, query, orderBy, limit, increment, serverTimestamp } =
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
    async getTop(n = 10){
      /* 只用單欄排序（score）以免需要複合索引；同分者在前端依時間先後排，
         多抓一些再截斷，確保同分時較早達成者排前面。 */
      try{
        const q = query(collection(db, "leaderboard"), orderBy("score", "desc"), limit(n * 3));
        const snap = await getDocs(q);
        const rows = snap.docs.map(d => ({id: d.id, ...d.data()}));
        rows.sort((a, b) =>
          (b.score - a.score) ||
          ((a.at && a.at.seconds || 0) - (b.at && b.at.seconds || 0)));
        return rows.slice(0, n);
      }catch(e){ console.debug("leaderboard read", e); return null; }
    },
    async submitScore(name, score, rounds){
      try{
        if(!auth.currentUser) await signInAnonymously(auth);   // 匿名身分即可，仍不需個資
        const clean = String(name || "").trim().slice(0, 16) || "匿名者";
        await addDoc(collection(db, "leaderboard"), {
          name: clean, score: Math.max(0, Math.min(100, score|0)),
          rounds: rounds|0, at: serverTimestamp(),
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
