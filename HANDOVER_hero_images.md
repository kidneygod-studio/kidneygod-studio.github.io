# 交班給 Codex：重做七張長文配圖

寫給 Codex 的一次性工作單（2026-09-26，Claude Code 整理）。
做完之後這個檔案可以刪掉，或把「已完成」那欄打勾留著當紀錄。

守則見 `AGENTS.md` 第六節；這份是那一節的補充，只針對這次要重做的圖。

---

## 為什麼要重做

首頁改成雜誌版之後，封面故事的圖會用到 **980×551** 的大尺寸顯示，
比以前的卡片大很多。原本在小卡片裡看不出來的問題，放大之後就很明顯：

- **3D 醫學示意圖**（發光的藍色腎臟、漂浮的試管）在一整排實拍風格的圖裡非常突兀
- **木製腎臟模型**這個道具被用了三次（01、04、22），一看就是同一組素材
- 有幾張的主體離畫面邊緣太近，在小卡片裡會被切到

**作者已確認要重做。** 不必等再問一次。

---

## 要重做的七張

| # | 檔名（slug） | 文章 | 現在的問題 | 目標 |
|---|---|---|---|---|
| 1 | `cystatin-c-egfr` | 胱抑素 C 與 eGFR 公式 | **發光藍色 3D 腎臟＋漂浮試管**，廉價醫學素材感最重的一張 | 改成實拍風：檢驗單與抽血試管在桌上 |
| 2 | `acei-arb-creatinine-rise` | 降血壓藥與肌酸酐 | 木製腎臟模型道具（三張重複之一） | 血壓計與藥盒，去掉腎臟模型 |
| 3 | `ckd-warning-signs` | 泡水高貧倦 | 木製腎臟模型＋放大鏡，過於直白 | 清晨窗邊的安靜生活場景 |
| 4 | `sglt2-kidney-protection` | SGLT2 抑制劑 | 木製腎臟模型（第三次） | 藥袋與藥盒的日常用藥場景 |
| 5 | `egfr-meaning-ckd-stages` | eGFR 判讀 | 三支試管＋信封，構圖空洞、意義不明 | 檢驗報告與老花眼鏡 |
| 6 | `dialysis-access-preparation` | 廔管提前準備 | 戶外逆光人像，**和「廔管準備」沒有關聯**，人物過小 | 診間衛教的手部特寫情境 |
| 7 | `home-bg` | 首頁背景 | 抽象藍色水波，通用素材感 | 低調的淺色紋理，不搶內容 |

**其餘 16 張維持原狀，不要動。** 尤其 `creatinine-high-what-to-do`、
`taiwan-eating-out-sodium`、`protein-intake-ckd` 已經很好，那三張現在就在首頁上。

---

## 規格（每一條都有理由，不要省）

檔名 **必須等於上表的 slug**，副檔名 `.jpg`／`.png`／`.webp` 都可以，
放進 `hero_src/`（**已 gitignore，不要提交原圖**）。

- **16:9，至少 1600×900**，建議 2752×1536 這種等級。
  `og/` 是從原圖裁的，像素多一點比較銳利。
- **主體壓在畫面中間 60%。** 分享預覽圖會中央裁成 1200×630，LINE 還會裁得更接近
  1:1；主體偏邊就會被切掉。**這次有三張就是栽在這裡。**
- **圖上不要有任何文字。** 生圖工具的中文幾乎都是壞的，而且會被上面那個裁切切斷。
  報告單、藥袋上的字請讓它模糊到看不出內容。
- **統一走實拍攝影風格**，不要 3D 渲染、不要發光特效、不要資訊圖表風。
  現有的好圖都是「自然光、淺景深、居家或診間」這個調性，新的要能混進去。
- **不要畫成動作教學或醫療示範**，不要出現可辨識的真人臉孔、病歷、檢驗數值。
- **不要重複使用同一個道具。** 木製腎臟模型這次全部拿掉，不要再出現。

---

## 建議的 prompt（可直接用，也可以自己改寫）

**1. cystatin-c-egfr**
> Editorial photo, 16:9, 2752x1536. A printed laboratory report sheet lying on a clean desk beside two capped blood collection tubes, soft diffused daylight, shallow depth of field, muted blue-grey clinical palette. Subject centred within the middle 60% of frame. Text on the report must be blurred and illegible. Photographic realism, no 3D render, no glowing effects, no anatomical models. No people.

**2. acei-arb-creatinine-rise**
> Editorial photo, 16:9, 2752x1536. A home blood-pressure monitor with its cuff coiled beside a weekly pill organiser on a warm wooden table, soft morning light from a window, shallow depth of field. Subject centred within the middle 60% of frame. Monitor display blank, no digits, no text anywhere. No people, no anatomical models.

**3. ckd-warning-signs**
> Editorial photo, 16:9, 2752x1536. A quiet domestic morning scene: a glass of water and a folded hand towel on a windowsill, soft early light, gentle shadows, calm muted palette. Subject centred within the middle 60% of frame. Not clinical, not alarming. No text, no people, no medical equipment, no toilets.

**4. sglt2-kidney-protection**
> Editorial photo, 16:9, 2752x1536. A white pharmacy medicine bag and a small white pill bottle resting on a plain light-grey table, soft diffused daylight, shallow depth of field, calm clinical palette. Subject centred within the middle 60% of frame. All printed text blurred and illegible. No people, no anatomical models, no 3D render.

**5. egfr-meaning-ckd-stages**
> Editorial photo, 16:9, 2752x1536. A health check-up report resting on a wooden desk with a pair of reading glasses placed on top, warm afternoon light, shallow depth of field. Subject centred within the middle 60% of frame. All printed text blurred and illegible — no readable numbers. No people.

**6. dialysis-access-preparation**
> Editorial photo, 16:9, 2752x1536. Close-up of a forearm resting on a clinic consultation desk, seen from the side, with a clinician's hands gesturing in explanation nearby; faces out of frame. Soft indoor light, calm and reassuring, shallow depth of field. Subject centred within the middle 60% of frame. No visible needles, no blood, no wounds, no text. Not a procedure demonstration.

**7. home-bg**
> Abstract background texture, 16:9, 2752x1536. Very soft out-of-focus warm paper texture in pale neutral tones, extremely low contrast, no discernible objects. Designed to sit behind text without competing with it. No blue water, no waves, no glowing effects, no text.

---

## 圖進來之後

```bash
python make_hero.py      # hero_src/<slug>.* → hero/<slug>.jpg（1600×900）
python make_og.py        # og/<slug>.jpg（1200×630 分享預覽圖）
python build_site.py
python bump_assets.py    # ⚠ 一定要跑
python check_site.py
```

**`bump_assets.py` 不能漏。** `hero/` 與 `og/` 在 `sw.js` 走快取優先且不看 `?v=`，
漏跑的話造訪過的人**永遠**看到舊圖，而且不會有任何錯誤訊息。

跑完在 CHANGELOG.md 最上面加一則，寫清楚換了哪幾張、為什麼。
