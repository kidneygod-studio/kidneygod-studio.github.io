# 給 AI 助手的工作守則（Claude Code / Codex 共用）

這個 repo 由作者（吳政哲醫師）、Claude Code、Codex 三方共同編輯，另外還有
**排程機器人每天自動寫入**。這份檔案是三方共同的規則，不是建議。

Codex 會自動讀這個檔；Claude Code 從 `CLAUDE.md` 轉過來也是讀這一份。
**只維護這一份，不要另外寫一份給自己看的。**

歷史紀錄在 `CHANGELOG.md`（那裡寫「為什麼」，這裡寫「怎麼做」）。

---

## 一、這個 repo 裡有三個不相干的網站

| 網址 | 目錄 | 產生器 | 狀態 |
|---|---|---|---|
| kidneygod.net | repo 根目錄 | `build_site.py` | 已上線，主力 |
| kidneygod.net/dialysis/ | `dialysis/` | `build_dialysis.py` | **尚未公開**，等醫院公關室 |
| kidneygod.net/tainanfood/ | `tainanfood/` | 來源在桌面，見下 | 已上線 |

**三個站不共用樣式、內容互不相干。** 改其中一個時不要順手「統一」另一個的
風格或導覽列——那是刻意分開的。

**唯一的例外是連結**（2026-09-23 作者指示）：衛教站的抽屜選單、頁尾、
食物查詢頁會連到 `/tainanfood/`，`build_site.py` 的 `FOOD_TOUR_*` 常數控制。
一律 `target="_blank"`——美食通那邊沒有連回來的入口（它的來源在桌面，
不能從這個 repo 改），同分頁跳過去讀者就回不來了。反方向的連結還沒做。

---

## 二、開工前 / 收工前（協作規則，最重要）

```bash
git pull --rebase origin main     # 開工第一件事
git status                        # 確認你要改的檔案沒有別人的未提交變更
```

**收工時工作區必須是乾淨的。** 不要留未提交的改動過夜——排程半夜會跑，
另一個 AI 隔天早上會接手，留著的髒東西會被誤當成自己的改動一起提交。

### 禁止 `git add -A` / `git add .`

只 stage 你自己動過的檔案，逐一列出。這條有實際事故：
未完成的長文被掃進一個「透析中心文案微調」的 commit，og 圖還沒產生就上線了。

### 看到這些檔案是 `M` 但不是你改的，**不要碰、不要提交**

```
articles_src/news.json   articles/news-*.html   articles/news.html
index.html   search_index.json   sw.js   sitemap.xml   robots.txt
```

這是每天 07:00 `NephrologyDailyDigest` 排程的產出，由 `publish_daily.py`
**自動建置、驗證、提交、推上線**（2026-09-23 起作者確認新知一律自動發佈，
不再經 Telegram 人工放行）。它的髒檔案檢查只看 `articles_src/news.json`，
所以不會被你擋住；你也不需要替它發佈。

**如果你重建了 `index.html`，它會自動吃進排程尚未提交的新知。** 這種情況
請在 commit 訊息裡明講，不要假裝沒發生。

自動發佈的安全網只有 `check_site.py`（沒過就不推）和建置本身會不會失敗。
所以**不要讓建置的診斷訊息變成會拋例外的那一段**——見下面的 cp950 那條。

### commit 訊息用中文，動詞開頭，說「改了什麼」

```
首頁改版：常用入口前移與精選衛教文章
```

不要寫 `fix`、`update`、`chore:`。這個 repo 的歷史是寫給人看的。

### 每次有意義的改動都要在 `CHANGELOG.md` 最上面加一則

格式看現有的。重點寫**為什麼這樣改、踩到什麼坑**，不是寫改了哪幾行
（那個 `git diff` 就有）。沒有坑的小改動可以不寫。

---

## 三、改東西之前：先確認你改的是「來源」還是「產出」

改到產出，下次重跑產生器就被蓋掉，**而且不會有任何警告**。
完整對照表在 `CHANGELOG.md` 開頭第一張表，先去看那張。

摘要：

- `articles/*.html`、`index.html`、`about.html`、`calc.html`、`food.html`、
  `legal.html` ← `build_site.py` 產生，來源是 `knowledge_export.json`
  和 `articles_src/*.md`
- **手寫、不由產生器管的**：`shop.html`、`game.html`、`library.html`、`dash.html`
- `dialysis/` 全部 ← `build_dialysis.py`（事實資料寫在該檔的 `FACTS` 字典）

### 改完一定要跑這三個

```bash
python build_site.py      # 內容有改
python bump_assets.py     # 資產有改（圖片、js、任何頁面）
python check_site.py      # 推之前對帳，沒過就別推
```

`check_site.py` 查的都是「不會噴錯、只會讓使用者看到舊的或錯的東西」那一類
問題，每一項都對應一次真實事故。它回傳 1 就不要推。

---

## 四、地雷（都是被咬過的）

**Service Worker 快取**：`sw.js` 對圖片、`hero/`、`og/` 是快取優先且
**不看 `?v=` 查詢字串**。換了圖卻沒跑 `bump_assets.py`，造訪過的人
**永遠**看到舊圖，沒有錯誤訊息。`/dialysis/` 與 `/tainanfood/` 已在
`sw.js` 明確排除（它們有自己的 SW），不要移除那兩行。

**印出來的訊息不可以讓程式死掉**：排程是用 `powershell.exe` 跑的，stdout 是
**cp950**，印中文以外的符號（`⚠`、日文假名、`�`）會 UnicodeEncodeError。
每支會被排程呼叫的腳本開頭都要有 `sys.stdout.reconfigure(encoding="utf-8")`。
2026-09-23 就是 `build_site.py` 少了這行：新匯入的一篇新知主題是空的，觸發
一則含 `⚠` 的警告，**建站在寫出 index.html 之前就崩潰**，每日新知發佈失敗，
而 log 裡只看得到 "BUILD FAILED:" 和一段 traceback（因為連錯誤訊息都印不出來）。
在 UTF-8 終端手動跑完全正常，所以只有無人值守時會中。

**`bump_assets.py` 雜湊的是檔案位元組**，這台 Windows 是 `core.autocrlf=true`
（JS 檔存成 CRLF）。換機器或換成 LF 會讓所有 `?v=` 全部變動，產生一批
看起來莫名其妙的 diff。看到只有 `?v=` 在變，那就是這個原因，不是有人亂改。

**CSS 變數別混用**：衛教站（根目錄）用 `--fg`，卡片區用 `--ink`。混用不會
報錯，只會在深色模式下變成看不見的字。

**`dialysis/` 的 `PUBLISH = False`**（`build_dialysis.py:269`）。
**不要自己改成 True。** 上線前還有四件事沒跟醫院確認：機器的三個選配功能、
技術員人數（站上寫 2、醫院官網寫 3）、聯絡窗口的姓名/LINE/手機能不能公開、
`NOTICE_CHECKED` 要更新。這是真實醫療機構的公開資訊，錯了有後果。

**不要憑空生出醫療機構的事實。** 機器型號、人數、時段、交通，沒有來源就
去問作者，不要推測，也不要抄廠商的宣傳詞（「業界領先」那種一律不要）。
曾經把代理商當成製造商寫上去（實際上機器是日本 NIPRO）。

**病患資料一律不進這個 repo。** 任何病歷號、床號、姓名、檢驗值都不行。

**金鑰不寫進檔案、不寫進 CHANGELOG、不印在輸出裡。**

---

## 五、台南美食通（`tainanfood/`）

**這裡的 `tainanfood/` 是產出，來源在 `C:\Users\user\Desktop\台南美食通`。**

`deploy.py` 會 `shutil.rmtree` 整個 `tainanfood/` 再重建。直接改這裡的檔案
下次部署會被**整個刪掉**，連 git 紀錄都救不回你沒提交的部分。

流程：改桌面那邊的 `data/raw/*.json` → `py build_static.py` → `py deploy.py --push`
（新增店家的欄位規格看該資料夾的 `data/SPEC.md`）

**照片授權**（2026-09-24 起改用 Google Places API，取代原本的示意圖做法）：

- 店家照片一律走 **Google Places API (New)**，網址帶 `browser_key` **即時向 API 取得**。
  Google 條款不允許下載存檔：place_id 可永久保存，其餘欄位（評分、時間、照片名稱）
  最多快取 30 天，所以要定期重跑桌面那邊的 `fetch_places.py`。
- **每張照片都必須顯示拍攝者**（版面上的 `.gcredit`）。那是授權條件，不要為了畫面乾淨拿掉。
- **仍然禁止**：把 Google／IG／FB 上網友的照片**下載下來自己存檔或修圖再用**，
  著作權屬拍攝者，經第三方服務（SerpApi 之類）轉手也一樣不行。
- 哪張照片拍到招牌菜要靠看圖判讀（`pick_photos.py`）。**小模型會判錯**：
  Haiku 初審把炒鱔魚意麵判成棺材板、白肉羹判成虱目魚肚粥，也沒濾掉浮水印，
  一定要用 Sonnet 以上複審。有部落客 logo、相機日期戳記的一律不用。
- 找不到合格照片的店**留空**，退回文字封面，不要拿別家店或同類料理的照片充數。
- IG／Threads 貼文用平台官方 `/embed` iframe（不是 embed.js）。
- 評論內容一律歸納改寫，不逐字轉貼。

**健康美食之旅 `/tainanfood/plan/`**：278 道菜的鈉／鉀／蛋白質／熱量／磷是
**依典型食譜推估**（食藥署資料庫查不到店家現做的成品），頁面已標明誤差可達三成。
醫學界線沿用衛教站：鈉對所有人、限鉀 eGFR<30、限磷 eGFR<45、
**蛋白質不做紅綠燈**（CKD 要限制、透析要增加，方向相反）。改這塊前先看那份原則。

---

## 六、交接時互相要講清楚的事

在回覆作者時，如果你做了下面任何一件，明講：

- 動了另一個 AI 正在進行中的檔案（`git status` 有別人的暫存內容時）
- 重建產出時順帶吃進了排程未提交的內容
- 改了架構（例如把單頁 hash 路由改成每頁靜態），而 README 還沒更新
- `check_site.py` 沒過但仍然推了（要說明為什麼）

作者是腎臟科醫師，不是工程師。**講結論、講代價，不要列一堆選項。**
測不出來的事情不要宣稱測過了。
