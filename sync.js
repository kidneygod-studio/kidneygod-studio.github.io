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
  const { getFirestore, doc, getDoc, setDoc, deleteDoc } =
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

  onAuthStateChanged(auth, u => {
    user = u;
    const label = document.getElementById("loginLabel");
    if(u){ label.textContent = u.isAnonymous ? "匿名同步中" : "已同步"; pull(); }
    else { label.textContent = "登入"; }
  });

  document.getElementById("loginBtn").style.display = "";
}
