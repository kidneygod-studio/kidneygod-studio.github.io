"""把 knowledge_export.json 的衛教內容產生成可被搜尋引擎索引的靜態網頁。

為什麼需要這支程式：
  站上 60 篇衛教內容目前全部包在 data.js 裡、還鎖在腎元購買機制後面，
  Google 讀不到任何一個字。這支程式把同樣的內容輸出成純靜態 HTML，
  不需要 JavaScript 就能閱讀，搜尋引擎才索引得到。

架構（hub and spoke）：
  articles/index.html          總覽（hub）
  articles/<分類>.html          8 個分類主題頁，每頁彙整該分類全部內容（約 1,800 字）
  articles/<文章>.html          日後擴寫的單篇長文（放 articles_src/*.md 就會自動產生）
  sitemap.xml / robots.txt     搜尋引擎入口

為什麼是分類頁而不是 60 個單篇頁：
  單篇平均只有 182 字，屬於「薄內容」，在 Google 的醫療內容標準下不會有排名。
  彙整成分類頁後每頁約 1,800 字，才有機會。等單篇擴寫到 1,500 字以上，
  再放進 articles_src/ 獨立成頁。

用法：
    python build_site.py            產生檔案
    python build_site.py --serve    產生後開本機預覽
"""
from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "articles"
SRC_MD = ROOT / "articles_src"

# 自訂網域。改這一行之外，repo 根目錄要有對應的 CNAME 檔，
# 且註冊商的 DNS 要指向 GitHub Pages（見 SETUP 說明）。
BASE_URL = "https://kidneygod.net"

SITE_NAME = "護腎教室"

# 聯絡信箱。用途刻意限縮在媒體、轉載、演講與勘誤——不做個人醫療諮詢，
# 避免讀者寄來檢查數值而讓本站持有個資法第 6 條的特種個人資料。
# 收信靠 Porkbun 的網域轉發（MX 已指向 fwd1/fwd2.porkbun.com），
# 不需要另外架郵件伺服器。
CONTACT_EMAIL = "contact@kidneygod.net"

# Cloudflare Web Analytics 的 beacon token。
# 選它而不是 GA4 的理由：不放 cookie、不收集個人識別資料，
# 因此不需要同意橫幅，也不會和「本站不收集任何資料」的定位衝突。
# 留空時完全不輸出這段 script，網站行為不受影響。
# 取得方式：Cloudflare 免費帳號 → Web Analytics → Add a site → 複製 token。
ANALYTICS_TOKEN = "e44b1d39221d4a5085336497dbff3ce4"


# 累計瀏覽數。數字存在 Firestore 的 stats/site，全站每一頁載入都 +1。
# 不載入 Firebase SDK：讀寫各一個 fetch 就夠，為了一個數字拉整套 SDK 不划算。
#
# 未認證也能寫，靠安全規則守住——stats/site 只允許「views 剛好 +1、
# 且不得夾帶其他欄位」的更新，設任意值、減少、刪除、灌水都會被擋（已實測）。
#
# 這是頁面瀏覽數，不是不重複訪客數：重整一次就多一次。真正的流量分析看
# Cloudflare Web Analytics，這裡只是頁尾給讀者看的累計數字。
_FS = "https://firestore.googleapis.com/v1/projects/kidneygod-ea61e/databases/(default)"
_KEY = "AIzaSyCbwPTuDOYdE1TjTd7pzLI6GUXCOPpgJNU"   # 前端公開識別碼，非機密
VIEWS_DOC = f"{_FS}/documents/stats/site?key={_KEY}&mask.fieldPaths=views"
VIEWS_COMMIT = f"{_FS}/documents:commit?key={_KEY}"
VIEWS_PATH = "projects/kidneygod-ea61e/databases/(default)/documents/stats/site"

VIEWS_SCRIPT = """
<script>
(async () => {
  const box = document.getElementById("siteViews");
  if(!box) return;
  const show = n => {
    if(!isFinite(n) || n <= 0) return;
    box.querySelector("b").textContent = n.toLocaleString("zh-Hant-TW");
    box.style.display = "";
  };
  const readNum = d => parseInt(d?.fields?.views?.integerValue, 10);

  try{
    /* 未認證的 +1。Firestore 規則限定只能讓 views 加一，
       寫不進去時（規則有變、離線、被擋）就退回下面的單純讀取。 */
    const r = await fetch(VIEWS_COMMIT, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({writes: [{transform: {
        document: VIEWS_PATH,
        fieldTransforms: [{fieldPath: "views", increment: {integerValue: "1"}}]
      }}]})
    });
    if(r.ok){
      /* 寫入會把加完的新值回傳，省一次讀取 */
      const d = await r.json();
      const n = parseInt(d?.writeResults?.[0]?.transformResults?.[0]?.integerValue, 10);
      if(isFinite(n) && n > 0){ show(n); return; }
    }
    const r2 = await fetch(VIEWS_URL, {cache: "no-store"});
    if(r2.ok) show(readNum(await r2.json()));
  }catch(e){ /* 取不到就整塊不顯示——寧可沒有，也不要顯示壞掉的數字 */ }
})();
</script>
"""


def analytics_tag() -> str:
    if not ANALYTICS_TOKEN:
        return ""
    # 寫法對齊 Cloudflare 目前發的片段（type="module"，本身就是延後執行）
    return ('\n<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" '
            f'data-cf-beacon=\'{{"token": "{ANALYTICS_TOKEN}"}}\'></script>')

# ---------------------------------------------------------------------------
# 作者資訊：醫療類內容（YMYL）的搜尋排名高度依賴作者專業身分（E-E-A-T）。
# 匿名的醫療網站在 Google 眼中可信度低，很難排上去。
# 發布前請確認以下內容正確且你同意公開。
# ---------------------------------------------------------------------------
AUTHOR_NAME = "吳政哲"
AUTHOR_TITLE = "腎臟科醫師"
AUTHOR_BIO = ("腎臟科專科醫師，臨床工作以三高、慢性腎臟病與血液透析／腹膜透析為主。"
              "在這裡整理腎臟與三高相關的衛教內容，內容依據國際指引與期刊文獻，"
              "並持續更新。")

# 社群帳號。這裡同時餵給三個地方：頁尾連結、醫師簡介頁的可見連結，
# 以及 JSON-LD 的 sameAs —— sameAs 是告訴搜尋引擎「這些帳號跟本站是同一個實體」，
# 對「作者是誰」的判定有直接影響，醫療類內容尤其看重這點。
#
# note 顯示帳號代號而不是「現用／原帳號」之類的說明：兩個 IG 只差在代號，
# 直接把代號寫出來讀者自己分得出來，也不必在專業網站上交代帳號的來龍去脈。
# url 為 None 的項目會被自動略過，方便先留位置之後再補。
SOCIAL = [
    {"label": "Threads", "url": "https://www.threads.com/@kidney.godreborn",
     "note": "@kidney.godreborn"},
    {"label": "Instagram", "url": "https://www.instagram.com/kidney.god/",
     "note": "@kidney.god"},
    {"label": "Instagram", "url": "https://www.instagram.com/kidney.godreborn/",
     "note": "@kidney.godreborn"},
    {"label": "Facebook", "url": "https://www.facebook.com/kidneygod",
     "note": "粉絲專頁"},
]
SOCIAL_LIVE = [s for s in SOCIAL if s["url"]]

# 作者實體。每一頁的 author 欄位都指向同一個 @id，搜尋引擎才會把散落在
# 各頁的文章歸給同一個人，而不是二十幾個同名的作者。
#
# 內容全部取自簡介頁上已經公開、可查證的資歷——結構化資料的用途是讓機器
# 讀得懂人眼已經看得到的東西，不是拿來多宣稱什麼。
AUTHOR_ID = f"{BASE_URL}/about.html#author"


def author_ld(full: bool = False) -> dict:
    """文章頁用精簡版（靠 @id 接回完整版），簡介頁用 full=True 的完整版。"""
    d = {
        "@type": "Physician",
        "@id": AUTHOR_ID,
        "name": AUTHOR_NAME,
        "jobTitle": AUTHOR_TITLE,
        "url": f"{BASE_URL}/about.html",
        "medicalSpecialty": ["Nephrologic", "InternalMedicine"],
        "hasCredential": [
            {"@type": "EducationalOccupationalCredential",
             "credentialCategory": "專科醫師證書", "name": "腎臟科專科醫師"},
            {"@type": "EducationalOccupationalCredential",
             "credentialCategory": "專科醫師證書", "name": "內科專科醫師"},
            {"@type": "EducationalOccupationalCredential",
             "credentialCategory": "認證", "name": "戒菸治療醫師"},
            {"@type": "EducationalOccupationalCredential",
             "credentialCategory": "認證", "name": "糖尿病共同照護網醫師"},
        ],
        "worksFor": {"@type": "Hospital", "name": "郭綜合醫院",
                     "department": {"@type": "MedicalOrganization", "name": "腎臟內科"}},
        "alumniOf": {"@type": "CollegeOrUniversity", "name": "國立成功大學醫學系"},
        "memberOf": [
            {"@type": "Organization", "name": "台灣慢性腎臟病臨床診療指引編撰委員會"},
            {"@type": "MedicalOrganization", "name": "台灣腎臟醫學會"},
            {"@type": "MedicalOrganization", "name": "美國腎臟醫學會",
             "alternateName": "American Society of Nephrology"},
        ],
        "sameAs": [s["url"] for s in SOCIAL_LIVE],
    }
    if full:
        d["description"] = AUTHOR_BIO
        d["email"] = CONTACT_EMAIL
        d["knowsAbout"] = ["慢性腎臟病", "急性腎衰竭", "血液透析", "腹膜透析", "多囊腎",
                           "電解質異常", "高血壓", "糖尿病", "高血脂", "痛風",
                           "代謝症候群", "戒菸治療"]
    return d


def reviewed_ld() -> dict:
    """醫療內容專用的審閱欄位。Google 對 MedicalWebPage 明確支援這兩個欄位，
    是「這篇有醫師看過」最直接的機器可讀訊號。審閱者就是作者本人。"""
    return {"lastReviewed": TODAY, "reviewedBy": {"@id": AUTHOR_ID}}


DISCLAIMER = ("本站內容為一般健康衛教資訊，不針對任何個人提供診斷或治療建議，"
              "亦不能取代您與主治醫師的討論。若您有健康疑慮或正在服藥，"
              "請與您的醫師或藥師討論後再做決定。")

# 權威來源。每一條的網址都實際連過、確認標題正確且沒有被導走，
# 學會名稱一律用官網上的正式全名（例如糖尿病學會的正式名稱含「內分泌暨」）。
#
# 一律連學會的官方指引頁，不連期刊 DOI 全文：全文多半擋機器人或要付費，
# 對民眾讀者沒有意義，而且指引改版時學會頁面會跟著更新、DOI 不會。
SOURCES: dict[str, tuple[str, str, str]] = {
    # key: (顯示名稱, 網址, 機構)
    "kdigo_ckd": ("KDIGO 2024 慢性腎臟病評估與處置臨床指引",
                  "https://kdigo.org/guidelines/ckd-evaluation-and-management/", "KDIGO"),
    "kdigo_bp": ("KDIGO 2021 慢性腎臟病血壓管理臨床指引",
                 "https://kdigo.org/guidelines/blood-pressure-in-ckd/", "KDIGO"),
    "kdigo_dm": ("KDIGO 2022 慢性腎臟病糖尿病管理臨床指引",
                 "https://kdigo.org/guidelines/diabetes-ckd/", "KDIGO"),
    "kdigo_lipid": ("KDIGO 慢性腎臟病血脂管理臨床指引",
                    "https://kdigo.org/guidelines/lipids-in-ckd/", "KDIGO"),
    "aha_bp": ("2025 AHA/ACC 成人高血壓預防、偵測、評估與處置指引",
               "https://professional.heart.org/en/science-news/"
               "2025-high-blood-pressure-guideline", "American Heart Association"),
    "aha_lipid": ("2026 ACC/AHA 血脂異常處置指引",
                  "https://professional.heart.org/en/science-news/"
                  "2026-guideline-on-the-management-of-dyslipidemia",
                  "American Heart Association"),
    "ada_soc": ("ADA Standards of Care in Diabetes（糖尿病照護標準，每年更新）",
                "https://professional.diabetes.org/standards-of-care",
                "American Diabetes Association"),
    "tsn": ("台灣腎臟醫學會", "https://www.tsn.org.tw/", "台灣腎臟醫學會"),
    "tsoc": ("中華民國心臟學會", "https://www.tsoc.org.tw/", "中華民國心臟學會"),
    "endo_dm": ("中華民國內分泌暨糖尿病學會", "https://www.endo-dm.org.tw/",
                "中華民國內分泌暨糖尿病學會"),
    "hpa_kidney": ("國民健康署 腎臟病主題專區",
                   "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=217",
                   "衛生福利部國民健康署"),
    "hpa_3high": ("國民健康署 遠離腎臟病，控制三高是關鍵",
                  "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=4705&pid=17467",
                  "衛生福利部國民健康署"),
    "fda_tfnd": ("食品藥物管理署 食品營養成分資料庫",
                 "https://consumer.fda.gov.tw/Food/TFND.aspx?nodeID=178",
                 "衛生福利部食品藥物管理署"),
    "niddk": ("NIDDK 慢性腎臟病專區",
              "https://www.niddk.nih.gov/health-information/kidney-disease/"
              "chronic-kidney-disease-ckd",
              "National Institute of Diabetes and Digestive and Kidney Diseases"),
}

# 每頁 2–3 條。分類頁是十幾則知識卡的彙整、主題跨得廣，所以這裡標示的是
# 「整頁內容依據哪些指引」，不是逐句對應的參考文獻——措辭上要老實反映這件事。
PAGE_SOURCES: dict[str, list[str]] = {
    # 八個分類頁（用分類名當 key）
    "血壓管理": ["kdigo_bp", "aha_bp", "hpa_3high"],
    "血糖管理": ["kdigo_dm", "ada_soc", "endo_dm"],
    "血脂代謝": ["kdigo_lipid", "aha_lipid", "tsoc"],
    "飲食護腎": ["kdigo_ckd", "fda_tfnd", "hpa_kidney"],
    "檢查數值": ["kdigo_ckd", "tsn", "niddk"],
    "用藥安全": ["kdigo_ckd", "tsn", "niddk"],
    "生活習慣": ["kdigo_ckd", "hpa_kidney", "niddk"],
    "警訊與迷思": ["kdigo_ckd", "tsn", "hpa_kidney"],
    # 四篇長文（用 slug 當 key）
    "egfr-meaning-ckd-stages": ["kdigo_ckd", "tsn", "niddk"],
    "creatinine-high-what-to-do": ["kdigo_ckd", "tsn", "niddk"],
    "foamy-urine-proteinuria": ["kdigo_ckd", "tsn", "niddk"],
    "taiwan-eating-out-sodium": ["kdigo_ckd", "fda_tfnd", "hpa_kidney"],
    "painkiller-nsaid-kidney": ["kdigo_ckd", "tsn", "niddk"],
    "diabetes-kidney-disease": ["kdigo_dm", "ada_soc", "endo_dm"],
    "kidney-function-recovery": ["kdigo_ckd", "tsn", "hpa_kidney"],
    "home-blood-pressure-measurement": ["kdigo_bp", "aha_bp", "tsoc"],
    "cholesterol-report-ckd": ["kdigo_lipid", "aha_lipid", "tsoc"],
    "kidney-lifestyle-evidence": ["kdigo_ckd", "hpa_kidney", "niddk"],
    "kidney-replacement-therapy": ["kdigo_ckd", "tsn", "niddk"],
    "dialysis-access-preparation": ["kdigo_ckd", "tsn", "niddk"],
    "no-dialysis-therapy-claims": ["kdigo_ckd", "tsn", "hpa_kidney"],
}


def sources_html(keys: list[str]) -> str:
    """文末的參考來源區塊。外連一律 rel="nofollow noopener"：
    這些是佐證用的引用，不是要把權重推給對方，也避免被當成換連結。"""
    if not keys:
        return ""
    parts = []
    for k in keys:
        name, url, org = SOURCES[k]
        # 學會類來源的名稱本身就是機構名（例如「中華民國心臟學會」），
        # 再補一行機構會變成同一個名字印兩次，所以相同時就不印。
        sub = f'<span class="org">{esc(org)}</span>' if org != name else ""
        parts.append(f'<li><a href="{esc(url)}" target="_blank" '
                     f'rel="nofollow noopener">{esc(name)}</a>{sub}</li>')
    li = "".join(parts)
    return (f'<h2 class="backlink" id="refs">參考來源</h2>'
            f'<div class="refs"><p class="sd">本頁內容依據下列指引與官方資料整理，'
            f'指引改版時本頁會一併更新。</p><ul>{li}</ul></div>')


INTERVIEWS = ROOT / "interviews.json"


def load_interviews() -> dict:
    """讀取專家訪談稿。鍵與 PAGE_SOURCES 相同：分類頁用分類名，長文用 slug。

    檔名以底線開頭的鍵視為草稿，不會出現在網站上——與 articles_src 的規則
    一致。醫療內容掛別人的名字發布前必須先取得對方同意，留一個能寫進檔案
    但不會上線的狀態是必要的。
    """
    if not INTERVIEWS.exists():
        return {}
    try:
        data = json.loads(INTERVIEWS.read_text("utf-8"))
    except json.JSONDecodeError as e:
        print(f"  ！interviews.json 格式有誤，訪談區塊全部略過：{e}")
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def interview_html(item: dict | None) -> str:
    """文末的專家訪談區塊。沒有稿子就完全不輸出。

    刻意不留空占位：醫療衛教站掛一個空的「專家訪談」標題，讀者看到的是
    「這站沒做完」，對 YMYL 內容是扣分而不是加分。有稿才出現。
    """
    if not item:
        return ""
    qa = "".join(
        f'<div class="qa"><p class="q">{esc(x["q"])}</p>'
        + "".join(f"<p>{esc(p)}</p>" for p in x["a"].split("\n") if p.strip())
        + "</div>"
        for x in item.get("qa", []))
    if not qa:
        return ""
    who = esc(item.get("expert", ""))
    role = esc(item.get("role", ""))
    dated = f'　·　{esc(item["date"])}' if item.get("date") else ""
    note = (f'<p class="sd">{esc(item["note"])}</p>' if item.get("note") else "")
    return (f'<h2 class="backlink" id="interview">專家訪談</h2>'
            f'<div class="itv"><p class="who"><b>{who}</b>'
            f'<span class="role">{role}</span></p>'
            f'<p class="sd">受訪內容由受訪者確認後刊出{dated}</p>'
            f'{qa}{note}</div>')


def interviewee_ld(item: dict | None) -> dict | None:
    """把受訪者寫進結構化資料。

    schema.org 沒有 Interview 型別，硬套一個不存在的型別只會讓驗證器報錯，
    所以用 mentions 指出這頁提到了誰——這是能誠實表達的最貼近描述。
    """
    if not item or not item.get("expert"):
        return None
    p = {"@type": "Person", "name": item["expert"]}
    if item.get("role"):
        p["jobTitle"] = item["role"]
    if item.get("url"):
        p["url"] = item["url"]
    return p


ITV = load_interviews()


# 分享按鈕的圖示。品牌那三個用各平台官方的字符外形（取自 simple-icons，圖示
# 資料以 CC0 釋出；商標權仍屬各品牌，此處用途是「連向該平台的分享按鈕」，
# 屬各平台品牌規範允許的用法）。刻意不自己畫近似品——畫歪的 logo 比純文字更糟。
#
# 全部內嵌成 SVG，執行時不對外發任何請求。
# fill 的用 filled 字符，stroke 的是自己畫的線條圖示，兩種畫法不能混。
ICONS = {
    "line": ("fill", "M19.365 9.863c.349 0 .63.285.63.631 0 .345-.281.63-.63.63H17.61v1.125h1.755c.349 0 .63.283.63.63 0 .344-.281.629-.63.629h-2.386c-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63h2.386c.346 0 .627.285.627.63 0 .349-.281.63-.63.63H17.61v1.125h1.755zm-3.855 3.016c0 .27-.174.51-.432.596-.064.021-.133.031-.199.031-.211 0-.391-.09-.51-.25l-2.443-3.317v2.94c0 .344-.279.629-.631.629-.346 0-.626-.285-.626-.629V8.108c0-.27.173-.51.43-.595.06-.023.136-.033.194-.033.195 0 .375.104.495.254l2.462 3.33V8.108c0-.345.282-.63.63-.63.345 0 .63.285.63.63v4.771zm-5.741 0c0 .344-.282.629-.631.629-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63.346 0 .628.285.628.63v4.771zm-2.466.629H4.917c-.345 0-.63-.285-.63-.629V8.108c0-.345.285-.63.63-.63.348 0 .63.285.63.63v4.141h1.756c.348 0 .629.283.629.63 0 .344-.282.629-.629.629M24 10.314C24 4.943 18.615.572 12 .572S0 4.943 0 10.314c0 4.811 4.27 8.842 10.035 9.608.391.082.923.258 1.058.59.12.301.079.766.038 1.08l-.164 1.02c-.045.301-.24 1.186 1.049.645 1.291-.539 6.916-4.078 9.436-6.975C23.176 14.393 24 12.458 24 10.314"),
    "fb": ("fill", "M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z"),
    "th": ("fill", "M18.263 11.097c-.03-3.486-1.92-5.586-5.111-5.586-2.13 0-3.922.963-4.863 2.499l2.062 1.438c.535-.843 1.272-1.543 2.628-1.543 1.528 0 2.318.85 2.544 2.431a15 15 0 0 0-2.236-.173c-4.125 0-6.068 1.867-6.068 4.336s1.943 3.99 4.804 3.99c3.139 0 5.013-2.115 5.781-4.735.798.361 1.348 1.204 1.348 2.47 0 3.387-3.907 5.232-7.22 5.232-4.885 0-8.077-3.207-8.077-8.424 0-6.392 4.223-10.487 9.9-10.487 3.808 0 5.69 1.671 6.97 3.914l2.108-1.475C21.44 2.078 18.331 0 13.663 0 6.227 0 1.168 5.277 1.168 12.934c0 7 4.953 11.066 10.856 11.066 4.878 0 9.809-2.846 9.809-7.716 0-2.545-1.46-4.231-3.569-5.187m-6.33 4.855c-1.077 0-2.026-.512-2.026-1.453 0-1.483 1.822-1.934 3.606-1.934.678 0 1.34.045 1.927.173-.422 1.927-1.671 3.215-3.508 3.214Z"),
    # 這三個不是品牌標誌，自己畫：鏈結、分享箭頭、打勾
    "copy": ("stroke", "M10.6 13.4a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1.4 1.4M13.4 10.6a4 4 0 0 0-5.66 0l-3 3a4 4 0 1 0 5.66 5.66l1.4-1.4"),
    "native": ("stroke", "M4 12v7a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7M12 3v13M12 3l-4 4M12 3l4 4"),
    "done": ("stroke", "M4 12.5l5.5 5.5L20 7"),
}


def icon(key: str, cls: str = "", hidden: bool = False) -> str:
    mode, d = ICONS[key]
    attrs = ('fill="currentColor"' if mode == "fill" else
             'fill="none" stroke="currentColor" stroke-width="2" '
             'stroke-linecap="round" stroke-linejoin="round"')
    return (f'<svg viewBox="0 0 24 24" width="19" height="19" aria-hidden="true"'
            f'{f" class={cls}" if cls else ""}{" hidden" if hidden else ""} '
            f'{attrs}><path d="{d}"/></svg>')


# 首頁分享時帶的標題。與首頁的 h1 一致，別人轉出去看到的名稱才對得上。
HOME_SHARE_TITLE = f"護腎專家－{AUTHOR_NAME}醫師的護腎教室"


def share_buttons(path: str, title: str, top: bool = False) -> str:
    """轉發按鈕。文章頂端與文末各放一組，內容相同。

    純圖示、不放文字：四顆帶文字的按鈕在 375px 手機上約需 445px，而可用寬度
    只有約 335px，排不成一排。圖示版每顆 44px，四顆加間距約 206px，綽綽有餘。
    文字拿掉之後靠 aria-label 與 title 保留語意，讀螢幕軟體與滑鼠停留都讀得到。

    用純連結的分享網址，不掛 Facebook／LINE 的官方外掛：那些能多做的只有顯示
    分享次數，卻要多載入數十 KB 的第三方腳本。連結版功能一樣完整。

    腳本只在文末那一組輸出一次，但會綁定頁面上所有的 .share——文末在文件後面，
    執行時兩組都已經存在。
    """
    url = f"{BASE_URL}/{re.sub(r'(^|/)index[.]html$', r'', path)}"
    u, t = urllib.parse.quote(url, safe=""), urllib.parse.quote(title, safe="")
    line = f"https://social-plugins.line.me/lineit/share?url={u}"
    fb = f"https://www.facebook.com/sharer/sharer.php?u={u}"
    th = f"https://www.threads.com/intent/post?text={t}%20{u}"

    def a(cls, href, label):
        return (f'<a class="sb {cls}" href="{href}" target="_blank" rel="noopener" '
                f'aria-label="分享到 {label}" title="分享到 {label}">{icon(cls)}</a>')

    btns = (
        f'<button class="sb native" type="button" hidden aria-label="分享" title="分享"'
        f' data-title="{esc(title)}" data-url="{esc(url)}">{icon("native")}</button>'
        + a("line", line, "LINE")
        + a("fb", fb, "Facebook")
        + a("th", th, "Threads")
        + f'<button class="sb copy" type="button" aria-label="複製連結" '
          f'title="複製連結" data-url="{esc(url)}">'
          f'{icon("copy", cls="i-off")}{icon("done", cls="i-on", hidden=True)}</button>'
    )
    head = "" if top else '<h2 class="backlink" id="share">分享這篇</h2>'
    note = "" if top else '<p class="sd">覺得有幫助的話，轉給需要的人。</p>'
    cls = "share top" if top else "share"
    return f'{head}<div class="{cls}">{note}<div class="sbtns">{btns}</div></div>'


def share_script() -> str:
    """綁定頁面上所有的 .share 區塊。整頁只輸出一次。"""
    return """
<script>
(function(){
  var boxes = document.querySelectorAll('.share');
  if (!boxes.length) return;
  Array.prototype.forEach.call(boxes, function(box){
    var copy = box.querySelector('.copy'), native = box.querySelector('.native');
    // 各平台的分享頁本來就是設計成用彈出視窗開啟的。當成整頁跳轉時，
    // Facebook 常常把人丟到動態牆而不是發文框——這是回報過的實際症狀。
    // 開不出彈窗（被瀏覽器擋、或手機不支援）就讓 <a> 原本的行為繼續。
    box.addEventListener('click', function(e){
      var a = e.target.closest && e.target.closest('a.sb');
      if (!a) return;
      var w = window.open(a.href, 'kgshare', 'width=600,height=540');
      if (!w) return;
      try { w.opener = null; } catch (err) {}   // window.open 不吃 rel=noopener
      e.preventDefault();
    });
    // 原生分享面板只在支援的瀏覽器（主要是手機）出現，桌機維持既有按鈕。
    // 它排第一顆：手機上這是最可靠的路徑，能直接叫出已安裝的 App。
    if (navigator.share) {
      native.hidden = false;
      // 收起 Facebook 的條件是「觸控裝置」，不是「有沒有 navigator.share」。
      // Windows 的 Chrome／Edge 桌機版也有 Web Share API，用它判斷會把桌機
      // 誤認成手機、連桌機的 Facebook 一起藏掉（實際發生過）。
      //
      // 真正的原因只在手機：facebook.com 是 FB App 宣告的網域，系統在載入
      // 網頁之前就把連結交給 App，而 App 不認得 sharer.php 的路徑，使用者
      // 會落在動態牆。這是 OS 層的決定，網頁端擋不掉。
      //
      // 而且要同時有 navigator.share 才收——否則等於把 Facebook 這條路
      // 完全拿掉，使用者連替代方案都沒有。
      var fbBtn = box.querySelector('a.fb');
      if (fbBtn && matchMedia('(pointer: coarse)').matches) fbBtn.hidden = true;
      native.addEventListener('click', function(){
        navigator.share({title: native.dataset.title, url: native.dataset.url})
          .catch(function(){});   // 使用者取消分享會 reject，不是錯誤
      });
    }
    copy.addEventListener('click', function(){
      // 純圖示按鈕沒有文字可以換，改成把鏈結圖示換成打勾。不要動
      // button.textContent——那會把裡面的 SVG 一起清掉且不會回來。
      var off = copy.querySelector('.i-off'), on = copy.querySelector('.i-on');
      var url = copy.dataset.url, done = function(){
        off.hidden = true; on.hidden = false;
        setTimeout(function(){ off.hidden = false; on.hidden = true; }, 1600);
      };
      // clipboard API 需要安全連線；不支援時退回舊做法，不要讓按鈕沒有反應
      if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(done, fallback);
      } else { fallback(); }
      function fallback(){
        var ta = document.createElement('textarea');
        ta.value = url; ta.setAttribute('readonly', '');
        ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        document.body.removeChild(ta);
      }
    });
  });
})();
</script>
"""


def citation_ld(keys: list[str]) -> list[dict]:
    """schema.org 的 citation 欄位，讓搜尋引擎讀得到這頁引用了哪些來源。"""
    return [{"@type": "CreativeWork", "name": SOURCES[k][0], "url": SOURCES[k][1],
             "publisher": {"@type": "Organization", "name": SOURCES[k][2]}}
            for k in keys]

CAT_SLUG = {
    "血壓管理": "blood-pressure",
    "血糖管理": "blood-sugar",
    "血脂代謝": "lipids",
    "飲食護腎": "diet",
    "用藥安全": "medication-safety",
    "生活習慣": "lifestyle",
    "檢查數值": "lab-values",
    "警訊與迷思": "myths",
}

CAT_INTRO = {
    "血壓管理": "血壓與腎臟是雙向的關係：高血壓會傷腎，腎功能變差又會讓血壓更難控制。這一頁整理血壓與腎臟之間最常被問到的問題。",
    "血糖管理": "糖尿病是台灣洗腎最主要的原因。血糖控制得好不好，直接決定腎臟能撐多久。這一頁整理血糖與腎臟的關聯與實際做法。",
    "血脂代謝": "血脂異常對腎臟的影響常被忽略，但它同時牽動心血管與腎臟的長期風險。這一頁整理血脂與腎臟保護的重點。",
    "飲食護腎": "「腎不好要吃什麼」是最常見的問題，答案卻會隨腎功能階段而改變。這一頁整理飲食上真正有證據的原則與常見誤解。",
    "用藥安全": "很多腎損傷來自可以避免的用藥。這一頁整理常見的傷腎藥物、危險組合，以及什麼情況下該先問過醫師。",
    "生活習慣": "腎臟的保養沒有捷徑，但有幾個生活習慣的影響比多數人想的大。這一頁整理實際有幫助的部分。",
    "檢查數值": "肌酸酐、eGFR、蛋白尿——健檢報告上的腎功能數字到底代表什麼。這一頁教你看懂自己的報告。",
    "警訊與迷思": "哪些症狀該就醫、哪些流傳很廣的說法其實沒有根據。這一頁整理腎臟相關的警訊與常見迷思。",
}

TODAY = date.today().isoformat()

# 頁首的品牌標記。用內嵌 SVG 而不是圖檔：縮放不糊、會跟著深淺色模式換色、
# 不多一次網路請求，而且商城的標誌是為深色底設計的，放在淺色頁面上不合適。
KIDNEY_SVG = (
    '<svg viewBox="0 0 24 24" width="25" height="25" fill="currentColor" aria-hidden="true">'
    '<path d="M13.6 2.6C8.4 2.6 4.4 6.7 4.4 12s4 9.4 9.2 9.4c2.9 0 5-1.6 5-3.8 '
    '0-1.9-1.4-2.9-2.8-3.6-.9-.5-1.5-.9-1.5-2s.6-1.5 1.5-2c1.4-.7 2.8-1.7 2.8-3.6 '
    '0-2.2-2.1-3.8-5-3.8Zm0 2c1.9 0 3 .8 3 1.8 0 .8-.7 1.3-1.7 1.8-1.3.7-2.6 1.6-2.6 '
    '3.8s1.3 3.1 2.6 3.8c1 .5 1.7 1 1.7 1.8 0 1-1.1 1.8-3 1.8-4 0-7.2-3.3-7.2-7.4S9.6 '
    '4.6 13.6 4.6Z"/></svg>'
)

CSS = """
:root{--bg:#fdfcfa;--fg:#22201d;--mut:#6b645c;--line:#e6e1d8;--card:#f6f3ed;
--accent:#0f766e;--accent2:#0d5f59;--warn:#8a5a00;--maxw:720px}
@media (prefers-color-scheme:dark){:root{--bg:#16140f;--fg:#eae5dc;--mut:#a3998a;
--line:#332e26;--card:#1e1b15;--accent:#5eead4;--accent2:#2dd4bf;--warn:#fbbf24}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:17px/1.85 -apple-system,"Segoe UI","Noto Sans TC","PingFang TC",sans-serif;
-webkit-text-size-adjust:100%}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 20px}
/* 錨點跳轉時要扣掉固定頁首的高度，否則標題會被壓在頁首下面。
   頁首約 60px，再加一點餘裕才不會貼著邊。 */
html{scroll-padding-top:78px}
header.site{position:sticky;top:0;z-index:50;background:var(--bg);
background:color-mix(in srgb,var(--bg) 86%,transparent);
backdrop-filter:saturate(150%) blur(10px);-webkit-backdrop-filter:saturate(150%) blur(10px);
border-bottom:1px solid var(--line);margin-bottom:8px}
header.site .wrap{display:flex;align-items:center;justify-content:space-between;
gap:14px;padding-top:11px;padding-bottom:11px}
.brand{display:inline-flex;align-items:center;gap:9px;text-decoration:none;
color:var(--fg);font-weight:800;font-size:1.04rem;letter-spacing:.3px;white-space:nowrap}
.brand svg{color:var(--accent);flex-shrink:0}
.brand:hover{color:var(--accent2)}
header.site nav{display:flex;align-items:center;gap:3px;flex-wrap:wrap;justify-content:flex-end}
header.site nav a{font-size:14px;color:var(--mut);text-decoration:none;font-weight:500;
padding:6px 11px;border-radius:8px;white-space:nowrap;
transition:color .15s,background .15s}
header.site nav a:hover{color:var(--fg);background:var(--card)}
header.site nav a[aria-current="page"]{color:var(--accent2);background:var(--card);font-weight:700}
/* 商城是另一個世界，用它自己的金色標示，一眼看得出不同 */
header.site nav a.shoplink{color:#2b2115;background:#e8c65a;font-weight:700}
header.site nav a.shoplink:hover{color:#2b2115;filter:brightness(1.07)}
/* 斷點是 700 不是 600：六個四字標籤加上品牌需要約 600px，
   在 640px 的視窗就會擠成兩行、頁首從 60px 變 101px。
   項目數增加時這個門檻要跟著往上調。 */
@media(max-width:700px){
  header.site .wrap{padding-top:8px;padding-bottom:8px;gap:8px}
  .brand{font-size:.95rem;gap:7px}
  .brand svg{width:22px;height:22px}
  header.site nav{gap:2px}
  /* 隱藏「衛教／關於／知識」前綴，只留兩個字，才排得下一行 */
  header.site nav .np{display:none}
  /* 五個項目時，10px 的水平內距會讓總寬超出約 1px 而換行，頁首從 66px 變 105px。
     縮到 8px 就排得下。垂直內距不動，點擊區高度不受影響。 */
  header.site nav a{padding:9px 8px;font-size:13.5px}
}
/* 小螢幕（iPhone SE 等 320–380px）再收一階，否則仍會換行 */
@media(max-width:380px){
  .brand{font-size:.88rem;gap:5px}
  .brand svg{width:20px;height:20px}
  header.site nav a{padding:9px 6px;font-size:12.5px}
}
/* 最小的一批（320px，iPhone SE 第一代）。六個項目時差 14px 才排得下，
   收水平內距與品牌字級即可，不必隱藏任何項目。
   垂直內距一律不動，點擊區高度維持 41px。 */
@media(max-width:340px){
  .brand{font-size:.8rem;gap:4px}
  .brand svg{width:18px;height:18px}
  header.site nav a{padding:9px 2px;font-size:12px}
  header.site nav{gap:0}
}
h1{font-size:1.85rem;line-height:1.35;margin:28px 0 10px;letter-spacing:-.01em}
/* 區塊標題左側的主色錨點。長文有 10–12 個 h2，這條線提供滑動時的節奏感，
   讓讀者知道換段了。用 flex-start 而非 center：標題換行時錨點對齊第一行，
   否則它會浮在整段的垂直中央，看起來像被漏掉。 */
h2{font-size:1.28rem;line-height:1.45;margin:38px 0 10px;padding-top:6px;
display:flex;align-items:flex-start;gap:10px}
h2::before{content:"";flex:0 0 auto;width:4px;height:1.05em;margin-top:.22em;
border-radius:2px;background:var(--accent)}
h3{font-size:1.05rem;margin:26px 0 8px;color:var(--mut)}
p{margin:0 0 18px}
a{color:var(--accent)}
.lede{font-size:1.06rem;color:var(--mut);margin-bottom:26px}
.meta{font-size:13.5px;color:var(--mut);margin:0 0 26px;padding-bottom:16px;border-bottom:1px solid var(--line)}
.toc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:26px 0}
/* 警示方塊。食物查詢與醫師簡介都用得到，所以放在共用樣式裡。
   色票要能跟著深色模式走，不能寫死。 */
:root{--wbg:#fff6f0;--wline:#c05621;--wttl:#9c4221}
@media (prefers-color-scheme:dark){
  :root{--wbg:#2a1b13;--wline:#c96a34;--wttl:#e9a97e}
}
.warnbox{background:var(--wbg);border-left:4px solid var(--wline);padding:16px 18px;
border-radius:0 8px 8px 0;margin:22px 0}
.warnbox b{color:var(--wttl);display:block;margin-bottom:8px;font-size:1.05rem}
.warnbox p{margin:0 0 8px;font-size:.96rem}
.warnbox p:last-child{margin:0}
.contact{font-size:1.12rem;font-weight:700;margin:0 0 18px}
/* 「本頁內容」是目錄方塊裡的小標籤，不是區塊標題，不加錨點 */
.toc h2{display:block;font-size:14px;margin:0 0 8px;color:var(--mut);text-transform:none}
.toc h2::before{content:none}
.toc ol{margin:0;padding-left:20px}
.toc li{margin:5px 0;font-size:15px}
article.card{border-top:1px solid var(--line);padding-top:6px}
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px;margin:26px 0}
.cats a{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;text-decoration:none;color:var(--fg)}
.cats a:hover{border-color:var(--accent)}
.cats .t{font-weight:700;margin-bottom:4px}
.cats .d{font-size:13.5px;color:var(--mut);line-height:1.6}
.author{display:flex;gap:14px;background:var(--card);border:1px solid var(--line);
border-radius:12px;padding:16px 18px;margin:40px 0 20px;font-size:14.5px;line-height:1.7}
.author .n{font-weight:700}
.author .n a{color:var(--fg);text-decoration:none}
.author .n a:hover{color:var(--accent);text-decoration:underline}
.author .r{color:var(--mut);font-size:13px}
/* 審閱資訊：讀者與搜尋引擎都在找「這篇有沒有醫師看過、什麼時候看的」，
   但它是佐證不是主文，所以壓小、放在簡介之後。 */
.author .rev{margin-top:8px;padding-top:8px;border-top:1px solid var(--line);
font-size:12.5px;color:var(--mut)}
.disclaimer{font-size:13.5px;color:var(--mut);background:var(--card);border-left:3px solid var(--warn);
padding:14px 16px;border-radius:0 8px 8px 0;margin:26px 0}
/* 參考來源：是佐證不是主文，所以整體壓小、用 --mut，但連結本身要看得出可以按。
   機構名另起一行當附屬資訊，避免和指引名稱在視覺上打架。 */
.refs ul{list-style:none;padding:0;margin:14px 0 0}
.refs li{padding:11px 0;border-top:1px solid var(--line);font-size:14px;line-height:1.6}
.refs li:first-child{border-top:0}
.refs li a{color:var(--fg);text-decoration:none;border-bottom:1px solid var(--line)}
.refs li a:hover{color:var(--accent);border-bottom-color:var(--accent)}
.refs .org{display:block;margin-top:3px;font-size:12.5px;color:var(--mut)}
/* 專家訪談：與內文明顯區隔，讀者要一眼看出「這段話是別人說的，不是本站」。
   用左側粗線而不是整塊底色，長篇問答鋪滿色塊會很沉重。 */
.itv{border-left:3px solid var(--accent);padding:2px 0 2px 18px;margin:14px 0 0}
.itv .who{margin:0 0 2px;font-size:16px}
.itv .who .role{margin-left:10px;font-size:13px;color:var(--mut);font-weight:400}
.itv .qa{margin-top:16px}
.itv .q{margin:0 0 6px;font-weight:700}
.itv .q::before{content:"Q　";color:var(--accent)}
.itv .qa p+p{margin-top:8px}
/* 轉發按鈕：外框樣式而非填色，文末已經有參考來源與延伸閱讀，
   再加一排實心色塊會太吵。手指目標維持 44px 高。 */
/* 純圖示、固定一排：帶文字的四顆在 375px 手機上約需 445px，可用寬度只有
   約 335px，排不成一排。圖示版每顆 44px、四顆加間距約 206px。
   nowrap 是刻意的——這排永遠不該換行。 */
.share .sbtns{display:flex;flex-wrap:nowrap;gap:10px;margin-top:14px}
.share.top{margin:18px 0 6px}
.share.top .sbtns{margin-top:0}
.sb{display:inline-flex;align-items:center;justify-content:center;
width:44px;height:44px;flex-shrink:0;border-radius:999px;cursor:pointer;
border:1.5px solid var(--line);background:var(--card);color:var(--fg);
transition:border-color .15s,color .15s}
.sb:hover{border-color:var(--accent);color:var(--accent)}
.sb svg{flex-shrink:0}
/* 這一行是必要的：hidden 屬性靠的是瀏覽器預設樣式的 display:none，而作者
   樣式優先於瀏覽器預設樣式，上面的 display:inline-flex 會把它蓋掉——結果
   是「隱藏」的按鈕照樣顯示出來，而且按了沒反應。 */
.sb[hidden],.sb svg[hidden]{display:none}
/* 各平台用自己的識別色只上在邊框與文字，不填滿——填滿會讓文末變成廣告帶 */
.sb.line:hover{border-color:#06c755;color:#06c755}
.sb.fb:hover{border-color:#0866ff;color:#0866ff}
.sb.th:hover{border-color:var(--fg);color:var(--fg)}
footer.site{border-top:1px solid var(--line);margin-top:50px;padding:24px 0 60px;
font-size:13.5px;color:var(--mut)}
footer.site a{color:var(--mut)}
.fcontact{margin:8px 0 0;display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px}
/* 選擇器要比 footer.site a（0,1,2）更明確，否則信箱會被壓成灰色 --mut，
   失去「這是可以按的東西」的視覺提示 */
footer.site .fcontact > a{font-weight:700;color:var(--fg)}
footer.site .fcontact .note{font-size:12.5px;color:var(--mut)}
.views{margin:10px 0 0;font-size:12.5px;color:var(--mut);
font-variant-numeric:tabular-nums}
.views b{color:var(--fg);font-weight:700}
.social{margin-top:10px;display:flex;flex-wrap:wrap;gap:8px 10px;align-items:center}
.social a{display:inline-flex;align-items:center;gap:6px;
padding:6px 13px;border:1px solid var(--line);border-radius:999px;
text-decoration:none;font-size:.92rem;color:var(--mut)}
.social a:hover{border-color:var(--fg);color:var(--fg)}
.social .nt{color:var(--mut);font-size:.8rem;opacity:.85}
.sociallist a{color:var(--fg)}
.backlink{margin:34px 0}
ul{padding-left:22px;margin:0 0 18px}
li{margin:7px 0}
strong{font-weight:700}
code{background:var(--card);padding:1px 6px;border-radius:5px;font-size:.92em}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;margin:22px 0}
table{width:100%;border-collapse:collapse;font-size:15px}
th,td{padding:9px 13px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{background:var(--card);font-weight:600;font-size:13.5px;color:var(--mut)}
tr:last-child td{border-bottom:0}
.callout{background:var(--card);border-left:3px solid var(--accent);
padding:14px 18px;border-radius:0 10px 10px 0;margin:22px 0;font-size:16px}

/* ── 衛教圖卡 ── */
.galnav{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 8px}
.galnav a{font-size:13.5px;background:var(--card);border:1px solid var(--line);
border-radius:99px;padding:6px 14px;text-decoration:none;color:var(--fg)}
.galnav a:hover{border-color:var(--accent)}
.galcard{display:grid;grid-template-columns:210px minmax(0,1fr);gap:22px;
padding:24px 0;border-top:1px solid var(--line);align-items:start}
.galcard:last-of-type{border-bottom:1px solid var(--line)}
.galcard img{width:100%;height:auto;aspect-ratio:1/1;object-fit:cover;
border-radius:10px;border:1px solid var(--line);display:block;background:var(--card);
transition:transform .16s,border-color .16s}
.galcard a.shot:hover img{transform:scale(1.02);border-color:var(--accent)}
.galcard h3{font-size:1.06rem;color:var(--fg);margin:0 0 8px;line-height:1.5}
/* 原文保留換行；貼文的分行本身就是作者安排的節奏，攤平會很難讀 */
.galcard .post{white-space:pre-wrap;font-size:15px;line-height:1.8;margin:0 0 10px}
.galcard .src{font-size:12.5px;color:var(--mut)}
/* 總覽頁：每個主題一塊，配四張縮圖預覽 */
.galgroup{display:block;text-decoration:none;color:inherit;margin:0 0 16px;
border:1px solid var(--line);border-radius:12px;padding:16px 18px;background:var(--card)}
.galgroup:hover{border-color:var(--accent)}
.gg-head{display:flex;justify-content:space-between;align-items:baseline;
gap:12px;margin-bottom:12px}
.gg-head b{font-size:1.08rem}
.gg-head span{font-size:13.5px;color:var(--mut);white-space:nowrap}
.gg-sub{font-size:13.5px;color:var(--mut);line-height:1.65;margin:-6px 0 12px}
/* Day 編號做成小標籤，一眼看得出這是一堂一堂連著的課 */
.galcard .day{display:inline-block;font-size:12px;font-weight:700;color:var(--accent2);
background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:1px 7px;margin-right:8px;vertical-align:2px}
.gg-prev{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.gg-prev img{width:100%;height:auto;aspect-ratio:1/1;object-fit:cover;
border-radius:7px;display:block;border:1px solid var(--line)}
@media(max-width:640px){
  .galcard{grid-template-columns:1fr;gap:14px;padding:20px 0}
  .galcard img{max-width:280px}
  .galcard .post{font-size:14.5px}
}

/* ── 醫師介紹（關於頁最上方）── */
.docintro{display:grid;grid-template-columns:minmax(0,300px) minmax(0,1fr);
gap:34px;align-items:center;margin:26px 0 40px}
.docintro.nophoto{grid-template-columns:1fr}
/* 原圖是全身直式，直接放會比旁邊的資歷欄高出一截。
   裁成 3:4 並把構圖重心往上移，取到頭部與上半身，和資歷欄的高度才平衡。
   想改成完整全身，把 aspect-ratio 與 object-fit 兩行拿掉即可。 */
/* height:auto 不可省略——HTML 上的 height 屬性（用來避免版面跳動）
   會被當成呈現提示而固定高度，那樣 aspect-ratio 就不會生效。 */
.docphoto{width:100%;height:auto;aspect-ratio:3/4;object-fit:cover;
object-position:center 12%;
border-radius:14px;display:block;box-shadow:0 10px 30px rgba(0,0,0,.16)}
.docname{font-size:1.9rem;font-weight:800;letter-spacing:.5px;margin:0 0 18px;
color:var(--accent2)}
.docname small{display:block;font-size:.95rem;font-weight:600;color:var(--mut);
letter-spacing:0;margin-bottom:4px}
/* 資歷分組：組名用小字級的全寬標籤，不搶項目本身的視線 */
.credgrp + .credgrp{margin-top:18px}
.credgrp h3{font-size:.82rem;font-weight:700;letter-spacing:1.5px;color:var(--mut);
margin:0 0 9px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.doccred{list-style:none;padding:0;margin:0}
.doccred li{display:flex;align-items:flex-start;gap:11px;margin:0 0 9px;
font-size:1.02rem;line-height:1.55}
.doccred li:last-child{margin-bottom:0}
.doccred svg{flex-shrink:0;margin-top:2px}
.doccred li.key{font-weight:700}
@media(max-width:720px){
  .docintro{grid-template-columns:1fr;gap:22px;margin-bottom:32px}
  .docphoto{max-width:250px;margin:0 auto}
  .docname{font-size:1.55rem;text-align:center}
  .doccred li{font-size:.98rem}
}

/* ── 首頁 ── */
.hero{padding:34px 0 8px}
.hero h1{font-size:2.1rem;margin:0 0 12px}
.hero .sub{font-size:1.08rem;color:var(--mut);margin-bottom:6px}
.hero .cred{font-size:14px;color:var(--mut)}
/* 首頁區塊標題：錨點由上方的 h2 通用規則提供，這裡只調字級與間距 */
.sect{font-size:1.15rem;margin:44px 0 4px}
.sect + .sd{font-size:14px;color:var(--mut);margin-bottom:16px;padding-left:14px}
/* 使用說明：定位在「先看這個再決定往哪走」，所以視覺上要跟一般段落分開，
   但又不能重到搶走主標題的位置 */
/* 原本是五行散文，在手機上佔掉 355px、將近半個第一屏，而且要讀完一句話
   才找得到連結。改成方塊：同樣的資訊約 180px，而且整格可點。
   順序刻意把商城放最後——衛教是主體，商城是其中一種學習方式。 */
/* 全站搜尋。索引在第一次點搜尋框時才載入，不拖慢首頁初次開啟。 */
.ssearch{position:relative;margin:18px 0 4px}
.svisually{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);
white-space:nowrap}
.ssearch input{width:100%;box-sizing:border-box;font:16px/1.5 inherit;
padding:13px 16px 13px 44px;border-radius:12px;color:var(--fg);background:var(--card);
border:1.5px solid var(--line);outline:none}
.ssearch input:focus{border-color:var(--accent)}
/* 放大鏡：純裝飾，pointer-events:none 才不會擋住點輸入框。
   左邊留 44px 的內距就是為了讓字不會壓到圖示。 */
.ssearch .sicon{position:absolute;left:15px;top:50%;transform:translateY(-50%);
width:18px;height:18px;color:var(--mut);pointer-events:none}
.ssearch input:focus ~ .sicon{color:var(--accent)}
/* 結果浮在內容之上，不把下面的版面推開——邊打字邊跳動很難用 */
.sres{position:absolute;left:0;right:0;top:calc(100% + 6px);z-index:40;
max-height:60vh;overflow-y:auto;background:var(--bg);border:1px solid var(--line);
border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,.12)}
.sres a{display:block;padding:11px 14px;text-decoration:none;color:var(--fg);
border-top:1px solid var(--line)}
.sres a:first-child{border-top:0}
.sres a:hover,.sres a:focus{background:var(--card)}
.sres .st{font-weight:700;font-size:15px;line-height:1.5}
.sres .sc{font-size:12px;color:var(--mut);margin-left:8px;font-weight:400;
white-space:nowrap}
.sres .sx{font-size:13px;color:var(--mut);line-height:1.6;margin-top:3px}
.sres mark{background:transparent;color:var(--accent);font-weight:700}
.sres .snone{padding:14px;font-size:14px;color:var(--mut)}
.howto{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:13px 14px;margin:20px 0 6px;color:var(--mut)}
.howto b{display:block;color:var(--fg);font-size:15.2px;margin-bottom:9px}
.hgrid{display:grid;gap:7px;grid-template-columns:1fr 1fr}
.htile{display:flex;flex-direction:column;text-decoration:none;
padding:8px 11px;border-radius:9px;background:var(--bg);
border:1px solid var(--line);border-left:3px solid var(--accent)}
.htile:hover{border-color:var(--accent);border-left-color:var(--accent)}
.htile .hq{font-size:12px;color:var(--mut);line-height:1.5}
.htile .hgo{font-size:15px;font-weight:700;color:var(--fg);line-height:1.45}
/* 六格剛好排滿三列，不需要讓最後一格獨佔整列。
   （若日後項目數變成奇數，再把 .htile:last-child{grid-column:1/-1} 加回來） */
/* 長文頁最上方的大圖，與首頁同一張。height:auto 同樣不能省——
   img 的 height 屬性會變成呈現屬性，把 aspect-ratio 壓掉（見下方註解）。 */
.ahero{width:100%;height:auto;aspect-ratio:16/9;object-fit:cover;display:block;
border-radius:14px;margin:18px 0 22px;background:var(--card)}
@media(max-width:700px){.ahero{border-radius:10px;margin:14px 0 18px}}

/* ── 深入文章的雜誌式陳列 ──
   每篇一張大圖（hero/<slug>.jpg），第一篇佔滿整排當封面。
   圖片是人工放進來的，缺圖時用同尺寸的漸層佔位塊，格線才不會塌。
   aspect-ratio 固定＋img 有 width/height，載入時不會位移（CLS）。 */
.mag{display:grid;gap:14px;grid-template-columns:repeat(auto-fill,minmax(258px,1fr));
margin-top:14px}
.mcard{display:block;text-decoration:none;color:inherit;background:var(--card);
border:1px solid var(--line);border-radius:14px;overflow:hidden;
transition:border-color .15s,transform .15s}
.mcard:hover{border-color:var(--accent);transform:translateY(-2px)}
/* height:auto 不能省。<img> 的 width/height 屬性會變成 CSS 呈現屬性
   （這裡是 height:900px），只覆寫 width 的話 aspect-ratio 會被那個高度壓過去，
   封面就變成 679x900 的巨大方塊。而且佔位塊是 <div>、沒有 height 屬性，
   所以「還沒放圖」的階段完全看不出來——2026-09-04 放圖上線才發現。 */
.mcard img,.mcard .mph{width:100%;height:auto;aspect-ratio:16/9;
object-fit:cover;display:block}
.mcard .mph{background:linear-gradient(135deg,var(--card) 0%,var(--line) 100%);
display:flex;align-items:center;justify-content:center}
.mcard .mph span{font-size:13px;font-weight:700;color:var(--mut);letter-spacing:2px}
.mcard .b{padding:13px 15px 16px}
.mcard .k{font-size:11.5px;font-weight:700;color:var(--accent);letter-spacing:1.2px;
margin-bottom:6px}
.mcard .t{font-weight:700;font-size:1.02rem;line-height:1.5;margin-bottom:5px}
.mcard .d{font-size:13.5px;color:var(--mut);line-height:1.65}
.mag .mcard.cover{grid-column:1/-1}
.mag .mcard.cover img,.mag .mcard.cover .mph{aspect-ratio:2.5/1}
.mag .mcard.cover .t{font-size:1.32rem}
.mag .mcard.cover .d{font-size:14.5px}
@media(max-width:640px){
  .mag{grid-template-columns:1fr;gap:12px}
  .mag .mcard.cover img,.mag .mcard.cover .mph{aspect-ratio:16/9}
  .mag .mcard.cover .t{font-size:1.12rem}
}

.feat{display:block;border:1px solid var(--line);border-radius:12px;padding:18px 20px;
text-decoration:none;color:var(--fg);background:var(--card);margin-bottom:12px}
.feat:hover{border-color:var(--accent)}
.feat .t{font-weight:700;font-size:1.05rem;margin-bottom:5px;line-height:1.5}
.feat .d{font-size:14px;color:var(--mut);line-height:1.65}

/* 商城入口：刻意沿用商城本身的深色＋金框風格，在淺色頁面上形成強烈對比，
   讓它成為整個首頁最醒目的元素。
   版面以標誌為主體、文字只作為說明它的圖說，所以是置中直排、不放按鈕與箭頭。 */
.gamebtn{display:flex;flex-direction:column;align-items:center;text-align:center;
gap:18px;text-decoration:none;
background:linear-gradient(120deg,#33281f,#1e1814);color:#e8c65a;
border:3px solid #c9a227;border-radius:18px;padding:32px 26px;margin:26px 0 10px;
box-shadow:inset 0 1px 0 rgba(255,236,200,.14),0 14px 34px rgba(0,0,0,.32);
position:relative;overflow:hidden;transition:transform .18s,box-shadow .18s}
.gamebtn:hover{transform:translateY(-4px);box-shadow:0 18px 42px rgba(201,162,39,.34)}
.gamebtn::after{content:"";position:absolute;top:0;left:-60%;width:40%;height:100%;
background:linear-gradient(100deg,transparent,rgba(255,240,200,.16),transparent);
animation:sheen 4.5s ease-in-out infinite}
@keyframes sheen{0%,72%{left:-60%}100%{left:130%}}
@media(prefers-reduced-motion:reduce){.gamebtn::after{animation:none}}
/* 標誌是橫幅比例，固定高度、寬度自動才不會被壓扁。
   這裡放的是白底原圖，直角白方塊貼在深色卡片上會像貼紙，
   加圓角讓它看起來是刻意擺上去的一張圖。 */
.gamebtn img{height:132px;width:auto;max-width:100%;border-radius:10px}
.gamebtn .cap{font-size:1.16rem;font-weight:800;color:#e8c65a;
letter-spacing:.4px;line-height:1.5}
@media(max-width:560px){
  .hero h1{font-size:1.68rem}
  .gamebtn{gap:14px;padding:26px 20px}
  .gamebtn img{height:92px}
  .gamebtn .cap{font-size:1.06rem}
}
"""


def slugify(s: str) -> str:
    s = re.sub(r"[^\w一-鿿-]+", "-", s.strip().lower())
    return re.sub(r"-{2,}", "-", s).strip("-")


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def social_links() -> str:
    """社群連結。兩個 IG 只差在帳號代號，所以代號一律顯示出來，
    否則頁尾會並排兩顆看起來一模一樣的「Instagram」。

    rel 用 me：這是 IndieWeb 的作者身分標記，部分工具會用它來驗證帳號歸屬，
    和 JSON-LD 的 sameAs 是互補的兩套機制。"""
    return "".join(
        f'<a href="{s["url"]}" rel="me noopener" target="_blank">{esc(s["label"])}'
        + (f'<span class="nt">{esc(s["note"])}</span>' if s.get("note") else "")
        + "</a>"
        for s in SOCIAL_LIVE)


def page(title: str, desc: str, path: str, body: str, jsonld: dict | None = None,
         extra_head: str = "", after_disclaimer: str = "") -> str:
    """所有頁面共用的骨架。canonical 與 OG 是搜尋引擎與分享預覽的基本要求。"""
    # canonical 必須和 sitemap 宣告的網址逐字相同，否則等於叫 Google 索引兩個位址。
    # sitemap 用的是目錄形式（/articles/），這裡把 index.html 收掉對齊。
    url = f"{BASE_URL}/{re.sub(r'(^|/)index\.html$', r'\1', path)}"

    # 分享預覽圖。檔名由網址推出來，og/ 底下的圖由 make_og.py 產生，
    # 兩邊用同一條規則命名，不必在每個呼叫點各自指定。
    og_slug = re.sub(r"[^a-z0-9]+", "-",
                     path.replace(".html", "").replace("/", "-")).strip("-") or "index"

    # 目前所在區塊要標示出來，讀者才知道自己在哪一層
    in_gallery = "gallery" in path
    in_articles = path.startswith("articles/") and not in_gallery
    cur = {"articles": in_articles, "gallery": in_gallery,
           "about": path == "about.html", "food": path == "food.html",
           "calc": path == "calc.html"}

    # 四字標籤在手機上會擠成兩行、頁首變高，所以其中兩個字包進 .np 於手機隱藏。
    # 多數項目是「前綴＋主詞」（衛教文章 → 文章），但「食物查詢」相反：
    # 手機上該留的是「食物」不是「查詢」，所以要能把隱藏的那半放在後面。
    def navlink(href: str, prefix: str, label: str, key: str, cls: str = "",
                suffix: str = "") -> str:
        mark = ' aria-current="page"' if cur.get(key) else ""
        c = f' class="{cls}"' if cls else ""
        pre = f'<span class="np">{prefix}</span>' if prefix else ""
        suf = f'<span class="np">{suffix}</span>' if suffix else ""
        return f'<a href="{href}"{c}{mark}>{pre}{label}{suf}</a>'

    # 手機上顯示：文章／圖卡／食物／計算／作者／遊戲
    nav = (navlink("/articles/", "衛教", "文章", "articles")
           + navlink("/articles/gallery.html", "衛教", "圖卡", "gallery")
           + navlink("/food.html", "", "食物", "food", suffix="查詢")
           + (navlink("/calc.html", "腎功能", "計算", "calc") if CALC_PUBLISHED else "")
           + navlink("/about.html", "關於", "作者", "about")
           + navlink("/shop.html", "護腎", "遊戲", "shop", "shoplink"))
    # 每一頁都掛：要的是全站瀏覽數，只算首頁會漏掉從搜尋直接進到某篇文章
    # 就離開的人——而那正是這個站大部分的流量。
    views_block = ('<p class="views" id="siteViews" style="display:none">'
                   '累計瀏覽 <b>–</b> 次</p>'
                   f'<script>const VIEWS_URL="{VIEWS_DOC}";'
                   f'const VIEWS_COMMIT="{VIEWS_COMMIT}";'
                   f'const VIEWS_PATH="{VIEWS_PATH}";</script>'
                   + VIEWS_SCRIPT)

    ld = f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ""
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BASE_URL}/og/{og_slug}.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(title)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<style>{CSS}</style>{extra_head}
{ld}
</head>
<body>
<header class="site"><div class="wrap">
<a class="brand" href="/">{KIDNEY_SVG}<span>{SITE_NAME}</span></a>
<nav>{nav}</nav>
</div></header>
<main class="wrap">
{body}
<div class="author">
  <div>
    <div class="n"><a href="/about.html">{esc(AUTHOR_NAME)}</a>　<span class="r">{esc(AUTHOR_TITLE)}</span></div>
    <div>{esc(AUTHOR_BIO)}</div>
    <div class="rev">本頁內容最後由{esc(AUTHOR_NAME)}醫師審閱於 {TODAY}　·　<a href="/about.html">完整資歷與撰寫原則</a></div>
  </div>
</div>
<div class="disclaimer">{esc(DISCLAIMER)}</div>
{after_disclaimer}
</main>
<footer class="site"><div class="wrap">
<p>{SITE_NAME}　·　最後更新 {TODAY}　·　<a href="/articles/">全部文章</a>　·　<a href="/">主站</a></p>
<!-- 用途說明跟著信箱一起出現。信箱會出現在每一頁，但完整的界線說明只在
     簡介頁，所以這裡帶一句最關鍵的，並連到完整版。 -->
<p class="fcontact"><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a>
<span class="note">媒體、轉載、演講、勘誤；<a href="/about.html#lian-luo">不提供個人醫療諮詢</a></span></p>
<p class="social">{social_links()}</p>
{views_block}
</div></footer>{analytics_tag()}
</body>
</html>
"""


def build_category(cat: str, items: list[dict],
                   articles: list[dict] | None = None) -> tuple[str, str, str]:
    slug = CAT_SLUG[cat]
    path = f"articles/{slug}.html"
    # 用冒號而不是「與」串接：分類名本身可能就含「與」（警訊與迷思），
    # 接成「警訊與迷思與腎臟健康」會讀不順。
    title = f"{cat}：腎臟健康的 {len(items)} 個重點整理｜{SITE_NAME}"
    intro = CAT_INTRO.get(cat, "")
    # description 同時要有足夠長度與關鍵字覆蓋，所以用「簡介＋前三篇標題」組成。
    # 中文搜尋結果約顯示 80 字，超過會被截斷，因此上限抓 150 字。
    heads = "、".join(it["title"] for it in items[:3])
    desc = f"{intro}內容包含：{heads} 等 {len(items)} 個主題。"
    desc = desc.replace("\n", " ")[:150]

    toc = "".join(
        f'<li><a href="#{slugify(it["id"])}">{esc(it["title"])}</a></li>' for it in items)
    secs = []
    for it in items:
        secs.append(
            f'<article class="card">'
            f'<h2 id="{slugify(it["id"])}">{esc(it["title"])}</h2>'
            f'<p>{esc(it["body"])}</p>'
            f'</article>')

    others = "".join(
        f'<a href="/articles/{CAT_SLUG[c]}.html"><div class="t">{esc(c)}</div>'
        f'<div class="d">{esc(CAT_INTRO.get(c, "")[:46])}…</div></a>'
        for c in CAT_SLUG if c != cat)

    # 內部連結：把屬於這個分類的長文列在最前面。
    # 分類頁流量較大，是把權重導向深度文章最自然的位置。
    deep = [a for a in (articles or []) if a.get("cat") == cat]
    deep_html = ""
    if deep:
        li = "".join(
            f'<a class="feat" href="/{a["path"]}"><div class="t">{esc(a["title"])}</div>'
            f'<div class="d">{esc(a["summary"][:88])}…</div></a>' for a in deep)
        deep_html = (f'<h2 class="backlink">深入閱讀</h2>'
                     f'<div class="sd">這個主題的完整長文</div>{li}')

    body = f"""
<h1>{esc(cat)}：腎臟健康重點整理</h1>
<p class="lede">{esc(intro)}</p>
<p class="meta">作者：<a href="/about.html">{esc(AUTHOR_NAME)}</a>（{esc(AUTHOR_TITLE)}）　·　更新於 {TODAY}　·　共 {len(items)} 則</p>
{share_buttons(path, f"{cat}：腎臟健康重點整理", top=True)}
{deep_html}
<div class="toc"><h2>本頁內容</h2><ol>{toc}</ol></div>
{''.join(secs)}
{interview_html(ITV.get(cat))}
{sources_html(PAGE_SOURCES.get(cat, []))}
{share_buttons(path, f"{cat}：腎臟健康重點整理")}{share_script()}
<h2 class="backlink">其他主題</h2>
<div class="cats">{others}</div>
"""

    jsonld = {
        "@context": "https://schema.org",
        "@type": "MedicalWebPage",
        "headline": f"{cat}：腎臟健康重點整理",
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/{path}",
        "dateModified": TODAY,
        "author": author_ld(),
        **reviewed_ld(),
        "publisher": {"@type": "Organization", "name": SITE_NAME},
        "about": {"@type": "MedicalCondition", "name": "慢性腎臟病"},
        "audience": {"@type": "PeopleAudience", "geographicArea": {"@type": "Country", "name": "台灣"}},
    }
    if cites := citation_ld(PAGE_SOURCES.get(cat, [])):
        jsonld["citation"] = cites
    if who := interviewee_ld(ITV.get(cat)):
        jsonld["mentions"] = who
    return path, page(title, desc, path, body, jsonld), title


def build_index(by_cat: dict[str, list[dict]], extra_pages: list[dict],
                n_gallery: int = 0) -> tuple[str, str]:
    path = "articles/index.html"
    title = f"腎臟與三高衛教文章總覽｜{SITE_NAME}"
    desc = ("腎臟科醫師整理的慢性腎臟病與三高衛教文章：血壓、血糖、血脂、飲食、用藥安全、"
            "檢查數值判讀與常見迷思，依據國際指引，持續更新。")
    cards = "".join(
        f'<a href="/articles/{CAT_SLUG[c]}.html">'
        f'<div class="t">{esc(c)}（{len(v)} 則）</div>'
        f'<div class="d">{esc(CAT_INTRO.get(c, "")[:52])}…</div></a>'
        for c, v in by_cat.items())
    # 長文原本在這裡只是一個 <ol> 編號清單，沒有摘要——而同一頁的衛教圖卡、
    # 以及首頁的同一個區塊，用的都是 .feat 卡片。長文是站上最有價值的內容，
    # 不該得到最陽春的呈現。（.toc 本來是分類頁「本頁內容」的頁內目錄樣式，
    # 拿來當文章列表在語意上也不對。）
    #
    # 2026-09-04：改成排在分類卡片之前，與首頁一致。順序一換，分類卡片就必須
    # 補一個「依主題閱讀」標題——原本它緊接在導言下面、沒有標題也讀得通，
    # 但被長文區隔開之後，沒有標題的一堆卡片會不知道自己是什麼。
    # 長文順序沿用 extra_pages（檔名序）：這頁是總覽，穩定的順序比「最新在前」
    # 更適合回頭查找；首頁才是要凸顯新內容的地方。
    extra = ""
    if extra_pages:
        cs = "".join(
            f'<a class="feat" href="/{a["path"]}">'
            f'<div class="t">{esc(a["title"])}</div>'
            f'<div class="d">{esc(a["summary"][:88])}…</div></a>'
            for a in extra_pages)
        extra = f"<h2>深入文章</h2><div class='sd'>完整長文，適合想把一個主題徹底搞懂的人</div>{cs}"

    gal = ""
    if n_gallery:
        gal = (f'<h2>衛教圖卡</h2>'
               f'<a class="feat" href="/articles/gallery.html">'
               f'<div class="t">{n_gallery} 張圖解，依主題分類</div>'
               f'<div class="d">原本發表在社群上的衛教圖，整理後收在這裡方便回頭查找。</div></a>')

    body = f"""
<h1>腎臟與三高衛教文章</h1>
<p class="lede">這裡整理慢性腎臟病、高血壓、糖尿病與高血脂相關的衛教內容，
依據國際指引與期刊文獻撰寫，目的是讓一般人也能看懂自己的身體與檢查報告。</p>
{extra}

<h2>依主題閱讀</h2>
<div class="sd">{sum(len(v) for v in by_cat.values())} 則衛教內容，分成 {len(by_cat)} 個主題，適合想直接找答案的人</div>
<div class="cats">{cards}</div>
{gal}
"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/{path}",
        "author": author_ld(),
    }
    return path, page(title, desc, path, body, jsonld)


def inline(s: str) -> str:
    """行內語法：**粗體**、`程式碼`、[文字](網址)。先跳脫再還原標記，避免注入。"""
    s = esc(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def md_to_html(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Markdown 區塊轉 HTML，同時回傳 h2 清單供產生目錄。

    中文段落內的換行直接接合、不補空格——否則中文字之間會出現空隙。
    支援：## / ### 標題、- 清單、| 表格、> 提示框，以及行內粗體與連結。
    """
    blocks = re.split(r"\n\s*\n", text.strip())
    out: list[str] = []
    heads: list[tuple[str, str]] = []

    for b in blocks:
        lines = [ln.rstrip() for ln in b.split("\n") if ln.strip()]
        if not lines:
            continue
        first = lines[0]

        if first.startswith("### "):
            out.append(f"<h3>{inline(first[4:].strip())}</h3>")
            if lines[1:]:
                out.append("<p>" + inline("".join(lines[1:])) + "</p>")
        elif first.startswith("## "):
            t = first[3:].strip()
            hid = slugify(t)
            heads.append((hid, t))
            out.append(f'<h2 id="{hid}">{inline(t)}</h2>')
            if lines[1:]:
                out.append("<p>" + inline("".join(lines[1:])) + "</p>")
        elif all(ln.startswith("- ") for ln in lines):
            items = "".join(f"<li>{inline(ln[2:].strip())}</li>" for ln in lines)
            out.append(f"<ul>{items}</ul>")
        elif first.startswith("|") and len(lines) >= 2:
            rows = [[c.strip() for c in ln.strip("|").split("|")] for ln in lines
                    if not re.fullmatch(r"\|[\s:|-]+\|", ln.strip())]
            if rows:
                th = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
                td = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                             for r in rows[1:])
                out.append(f'<div class="tw"><table><thead><tr>{th}</tr></thead>'
                           f"<tbody>{td}</tbody></table></div>")
        elif first.startswith("> "):
            body = "".join(ln.lstrip("> ").strip() for ln in lines)
            out.append(f'<div class="callout">{inline(body)}</div>')
        else:
            out.append("<p>" + inline("".join(lines)) + "</p>")

    return out, heads


PUB_DATES = SRC_MD / "published.json"


def load_pub_dates() -> dict[str, str]:
    """記住每篇文章第一次發布的日期。
    Google 會同時看 datePublished 與 dateModified；若只有後者，
    每次重新產生都會讓文章看起來像新寫的，反而不利於累積權重。"""
    if PUB_DATES.exists():
        try:
            return json.loads(PUB_DATES.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def extract_faq(text: str) -> list[tuple[str, str]]:
    """從「常見問題／常見誤解」段落抽出問答配對，用來產生 FAQPage 結構化資料。

    Google 會把 FAQPage 呈現成可展開的問答區塊，版位在一般搜尋結果之上。
    慣例：`## 常見問題`（或含「常見誤解」）底下，每個 `### 問句` 加緊接的段落。
    """
    m = re.search(r"^##\s+(.*(?:常見問題|常見誤解).*)$", text, re.M)
    if not m:
        return []
    section = text[m.end():]
    nxt = re.search(r"^##\s+", section, re.M)
    if nxt:
        section = section[:nxt.start()]

    faqs = []
    parts = re.split(r"^###\s+", section, flags=re.M)[1:]
    for p in parts:
        lines = [ln.strip() for ln in p.strip().split("\n") if ln.strip()]
        if len(lines) < 2:
            continue
        q = lines[0].strip("「」？?。 ")
        a = "".join(lines[1:])
        a = re.sub(r"\*\*([^*]+)\*\*", r"\1", a)
        faqs.append((lines[0].strip(), a))
    return faqs


def parse_article(md: Path) -> dict:
    """解析一篇 Markdown 長文。
    格式：`# 標題` / `> 一句話摘要` / `分類：檢查數值`（可省略）/ 內文。"""
    text = md.read_text(encoding="utf-8").strip()
    lines = text.split("\n")
    title = lines[0].lstrip("# ").strip() if lines else md.stem
    rest = lines[1:]

    summary, cat = "", ""
    while rest and not rest[0].strip():
        rest.pop(0)
    if rest and rest[0].startswith(">"):
        summary = rest.pop(0).lstrip("> ").strip()
    while rest and not rest[0].strip():
        rest.pop(0)
    if rest and re.match(r"^(分類|cat)\s*[:：]", rest[0]):
        cat = re.split(r"[:：]", rest.pop(0), maxsplit=1)[1].strip()

    return {"slug": md.stem, "title": title, "summary": summary,
            "cat": cat if cat in CAT_SLUG else "",
            "body": "\n".join(rest), "raw": text}


def build_markdown_articles() -> list[dict]:
    """articles_src/*.md 各自產生一頁長文。回傳每篇的中繼資料供互連與首頁使用。"""
    out: list[dict] = []
    if not SRC_MD.exists():
        return out

    pub = load_pub_dates()
    changed = False

    for md in sorted(SRC_MD.glob("*.md")):
        # 檔名以底線開頭 = 草稿，不產生頁面也不進 sitemap。
        # 醫學內容掛作者姓名發布前必須先經本人審核，審完把底線拿掉即可上線。
        if md.name.startswith("_"):
            print(f"  （草稿，未發布）{md.name}")
            continue

        a = parse_article(md)
        paras, heads = md_to_html(a["body"])
        toc = ""
        if len(heads) >= 3:
            li = "".join(f'<li><a href="#{h}">{esc(t)}</a></li>' for h, t in heads)
            toc = f'<div class="toc"><h2>本頁內容</h2><ol>{li}</ol></div>'

        path = f"articles/{a['slug']}.html"
        desc = (a["summary"] or a["title"])[:150]

        if a["slug"] not in pub:
            pub[a["slug"]] = TODAY
            changed = True
        published = pub[a["slug"]]
        a["published"] = published      # 首頁的雜誌式陳列要靠它排序（新的在前）

        datestr = (f"發布於 {published}" if published == TODAY
                   else f"發布於 {published}　·　更新於 {TODAY}")

        # 內部連結：把文章接回它所屬的分類頁，讓搜尋引擎看得出主題歸屬
        related = ""
        if a["cat"]:
            related = (f'<h2 class="backlink">延伸閱讀</h2>'
                       f'<div class="cats">'
                       f'<a href="/articles/{CAT_SLUG[a["cat"]]}.html">'
                       f'<div class="t">{esc(a["cat"])}：完整整理</div>'
                       f'<div class="d">{esc(CAT_INTRO.get(a["cat"], "")[:46])}…</div></a>'
                       f'<a href="/articles/"><div class="t">全部衛教主題</div>'
                       f'<div class="d">血壓、血糖、血脂、飲食、用藥安全…</div></a>'
                       f"</div>")

        body = f"<h1>{esc(a['title'])}</h1>"
        # 標題之後、導言之前放大圖，和首頁用同一張。純裝飾（alt 留空）——
        # 圖片本身沒有資訊量，標題與導言已經說完了，讀螢幕的人不需要再聽一次。
        hsrc, hdim = hero_for(path)
        if hsrc:
            hwh = f' width="{hdim[0]}" height="{hdim[1]}"' if hdim else ""
            body += (f'<img class="ahero" src="/{hsrc}"{hwh} alt="" aria-hidden="true" '
                     f'fetchpriority="high" decoding="async">')
        if a["summary"]:
            body += f"<p class='lede'>{esc(a['summary'])}</p>"
        refs = PAGE_SOURCES.get(a["slug"], [])
        itv = ITV.get(a["slug"])
        body += (f"<p class='meta'>作者：<a href='/about.html'>{esc(AUTHOR_NAME)}</a>"
                 f"（{esc(AUTHOR_TITLE)}）　·　{datestr}</p>"
                 + share_buttons(path, a["title"], top=True) + toc
                 + "".join(paras) + interview_html(itv) + sources_html(refs)
                 + share_buttons(path, a["title"]) + share_script() + related)

        jsonld = {
            "@context": "https://schema.org", "@type": "MedicalWebPage",
            "headline": a["title"], "description": desc, "inLanguage": "zh-Hant",
            "url": f"{BASE_URL}/{path}",
            "datePublished": published, "dateModified": TODAY,
            "author": author_ld(),
            **reviewed_ld(),
            "publisher": {"@type": "Organization", "name": SITE_NAME},
            "about": {"@type": "MedicalCondition", "name": "慢性腎臟病"},
        }
        if cites := citation_ld(refs):
            jsonld["citation"] = cites
        if who := interviewee_ld(itv):
            jsonld["mentions"] = who

        faqs = extract_faq(a["raw"])
        extra_ld = ""
        if faqs:
            faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
                      "mainEntity": [{"@type": "Question", "name": q,
                                      "acceptedAnswer": {"@type": "Answer", "text": ans}}
                                     for q, ans in faqs]}
            extra_ld = ('<script type="application/ld+json">'
                        + json.dumps(faq_ld, ensure_ascii=False) + "</script>")

        a["path"] = path
        a["html"] = page(f"{a['title']}｜{SITE_NAME}", desc, path, body, jsonld,
                         extra_head=extra_ld)
        a["faq_count"] = len(faqs)
        out.append(a)

    if changed:
        PUB_DATES.write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


SEARCH_INDEX = ROOT / "search_index.json"


def _plain(md: str) -> str:
    """把 markdown 壓成純文字，只供比對用，不會顯示原樣。"""
    md = re.sub(r"(?m)^\s*\|.*$", " ", md)          # 表格列
    md = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", md)   # 連結與圖片留文字
    md = re.sub(r"[#>*`_~\-]+", " ", md)
    return re.sub(r"\s+", " ", md).strip()


def build_search_index(data: list[dict], md_pages: list[dict],
                       gallery_items: list[dict]) -> int:
    """產生全站搜尋索引。**不含遊戲商城**——那是另一套內容與網址結構。

    為什麼用「建置時產生 JSON、前端比對」：GitHub Pages 是純靜態，沒有後端可以
    查詢。索引在首頁「使用者第一次點搜尋框時」才載入，不影響首頁初次開啟速度。

    中文沒有詞界，斷詞函式庫在這個資料量上帶來的準確度提升有限，卻要多載入
    數十 KB 並增加一個相依。直接做子字串比對對中文反而穩定，也不會有斷錯詞
    導致搜不到的情況。

    欄位刻意用單字母：這份檔案有數萬字，鍵名重複出現的成本不能忽略。
      t 標題　u 網址　c 分類　b 內文（比對與截取摘要用）
    """
    idx: list[dict] = []

    for it in data:                                   # 知識卡 → 分類頁的錨點
        cat = it["cat"]
        if cat not in CAT_SLUG:
            continue
        idx.append({"t": it["title"], "c": cat, "b": it["body"],
                    "u": f"/articles/{CAT_SLUG[cat]}.html#{slugify(it['id'])}"})

    for a in md_pages:                                # 長文
        idx.append({"t": a["title"], "c": a.get("cat") or "深入文章",
                    "b": (a.get("summary") or "") + " " + _plain(a["body"]),
                    "u": f"/articles/{a['slug']}.html"})

    for g in gallery_items:                           # 圖卡 → 該系列頁的錨點
        slug = g.get("series_slug")
        if not slug:
            continue
        # g:1 標記為圖卡。排序時稍微往後放——圖卡是配圖，同樣命中的情況下
        # 文字內容才是完整的答案。不標記的話，圖卡標題短、命中位置靠前，
        # 會把專門講那個主題的長文壓到後面。
        idx.append({"t": g.get("cap", ""), "c": g.get("cat") or "衛教圖卡",
                    "b": g.get("text", ""), "g": 1,
                    "u": f"/articles/gallery-{slug}.html#g-{g['id']}"})

    # 工具與導覽頁：使用者常直接搜「計算」「食物」而不是搜內容
    for t, u, c, b in [
        ("腎功能計算：eGFR 與腎衰竭風險", "/calc.html", "工具",
         "用 CKD-EPI 2021 公式計算 eGFR 與慢性腎臟病分期，並以 KFRE 估算腎衰竭風險。胱抑素 C"),
        ("食物營養查詢", "/food.html", "工具",
         "查 1,728 種食物的鈉、鉀、磷、蛋白質含量，資料來自衛福部食藥署食品營養成分資料庫。"),
        ("關於吳政哲醫師", "/about.html", "關於",
         "腎臟科專科醫師的資歷、撰寫原則與聯絡方式。"),
        ("全部衛教文章", "/articles/", "導覽", "依主題瀏覽所有衛教內容。"),
        ("衛教圖卡總覽", "/articles/gallery.html", "導覽", "社群上發表過的圖解，依主題整理。"),
    ]:
        idx.append({"t": t, "u": u, "c": c, "b": b})

    SEARCH_INDEX.write_text(
        json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return len(idx)


def build_home(by_cat: dict[str, list[dict]], extra: list[dict], n_gallery: int = 0) -> str:
    """網站首頁：以衛教內容為主，商城與遊戲收在一個明顯的大按鈕後面。"""
    title = f"護腎教室｜腎臟與三高衛教．{AUTHOR_NAME}{AUTHOR_TITLE}"
    desc = ("腎臟科醫師撰寫的慢性腎臟病與三高衛教：看懂 eGFR 與腎功能報告、"
            "血壓血糖血脂如何影響腎臟、傷腎藥物與飲食原則。依據國際指引，持續更新。")

    cards = "".join(
        f'<a href="/articles/{CAT_SLUG[c]}.html">'
        f'<div class="t">{esc(c)}（{len(v)} 則）</div>'
        f'<div class="d">{esc(CAT_INTRO.get(c, "")[:50])}…</div></a>'
        for c, v in by_cat.items())

    # 新的排前面，最新一篇當封面。原本沿用檔名排序（build_markdown_articles
    # 是 sorted glob），雜誌式陳列用字母序沒有意義——讀者期待的是「最新的在最上面」。
    # 只影響首頁的呈現順序，其他地方用到的 md_pages 不動。
    feed = sorted(extra, key=lambda a: (a.get("published", ""), a["path"]), reverse=True)
    feats = "".join(mag_card(a, i == 0) for i, a in enumerate(feed))

    feat_sect = (f'<h2 class="sect" id="deep">深入文章</h2>'
                 f'<div class="sd">完整長文，適合想把一個主題徹底搞懂的人</div>'
                 f'<div class="mag">{feats}</div>'
                 if feats else "")

    # 遊戲入口用白底原圖（作者指定），不是頁首那張去背的 logo.png。
    # 直接讀實際尺寸，換圖時不必再手改寫死的數字（換過一次比例就變了）
    lw = img_size(ROOT / "logo-white.png")
    logo_dims = f' width="{lw[0]}" height="{lw[1]}"' if lw else ""

    # 食物查詢：唯一的工具型內容，值得一個獨立入口。沒有 food_db.json 時整段消失。
    food_sect = ""
    if FOOD_DB.exists():
        n_food = len(json.loads(FOOD_DB.read_text(encoding="utf-8"))["rows"])
        food_sect = (f'<h2 class="sect" id="food">食物查詢</h2>'
                     f'<div class="sd">腎臟病飲食最需要注意的是鈉、鉀、磷、蛋白質，'
                     f'而該注意哪一項取決於你的分期</div>'
                     f'<a class="feat" href="/food.html">'
                     f'<div class="t">查 {n_food:,} 種食物的鈉、鉀、磷、蛋白質含量</div>'
                     f'<div class="d">資料來自衛福部食藥署食品營養成分資料庫。</div></a>')

    calc_sect = ""
    if CALC_PUBLISHED:
        calc_sect = ('<h2 class="sect" id="calc">腎功能計算</h2>'
                     '<div class="sd">把報告上已經有的數值換算成 eGFR 與分期</div>'
                     '<a class="feat" href="/calc.html">'
                     '<div class="t">eGFR 與腎衰竭風險計算</div>'
                     '<div class="d">CKD-EPI 2021 公式，填了胱抑素 C 會自動改用較準確的合併式；'
                     '第 3–5 期另可用 KFRE 估算腎衰竭風險。</div></a>')

    gal_sect = (f'<h2 class="sect" id="gallery">衛教圖卡</h2>'
                f'<div class="sd">社群上發表過的圖解，依主題整理並附上完整說明</div>'
                f'<a class="feat" href="/articles/gallery.html">'
                f'<div class="t">{n_gallery} 張衛教圖卡</div>'
                f'<div class="d">血壓、血糖、血脂、飲食、用藥安全、檢查數值…'
                f'點主題可跳到該區。</div></a>' if n_gallery else "")

    body = f"""
<div class="hero">
<h1>護腎專家－{esc(AUTHOR_NAME)}醫師的護腎教室</h1>
<p class="sub">把腎臟的事，講到你聽得懂。慢性腎臟病、高血壓、糖尿病、高血脂——
這裡用一般人看得懂的方式，說明檢查數字代表什麼、哪些習慣真的有影響、哪些說法沒有根據。</p>
<p class="cred">內容依據國際指引與期刊文獻撰寫，持續更新。
<a href="/about.html">關於{esc(AUTHOR_NAME)}醫師 →</a></p>

<div class="ssearch">
  <label class="svisually" for="sq">搜尋站內衛教內容</label>
  <input id="sq" type="search" autocomplete="off" spellcheck="false"
         placeholder="搜尋衛教內容，例如：蛋白尿、止痛藥、香蕉">
  <!-- 放在 input 後面才能用 input:focus ~ .sicon 換色；位置靠 absolute 拉到左邊 -->
  <svg class="sicon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="2" stroke-linecap="round" aria-hidden="true">
    <circle cx="11" cy="11" r="7"/><path d="M20 20l-4.3-4.3"/></svg>
  <div id="sres" class="sres" hidden></div>
</div>

<div class="howto">
<b>這個網站怎麼用</b>
<div class="hgrid">
  <a class="htile" href="#deep"><span class="hq">想徹底弄懂一件事</span>
    <span class="hgo">深入文章</span></a>
  <a class="htile" href="#topics"><span class="hq">有明確想查的問題</span>
    <span class="hgo">依主題閱讀</span></a>
  <a class="htile" href="/calc.html"><span class="hq">拿到報告想換算</span>
    <span class="hgo">腎功能計算</span></a>
  <a class="htile" href="/food.html"><span class="hq">想查某個食物</span>
    <span class="hgo">食物查詢</span></a>
  <a class="htile" href="#gallery"><span class="hq">只想快速看重點</span>
    <span class="hgo">衛教圖卡</span></a>
  <a class="htile" href="/shop.html"><span class="hq">不知道從哪開始</span>
    <span class="hgo">遊戲場</span></a>
</div>
</div>
{share_buttons("", HOME_SHARE_TITLE, top=True)}
</div>

{feat_sect}

<h2 class="sect" id="topics">依主題閱讀</h2>
<div class="sd">{sum(len(v) for v in by_cat.values())} 則衛教內容，分成 {len(by_cat)} 個主題，適合想直接找答案的人</div>
<div class="cats">{cards}</div>

{calc_sect}
{food_sect}
{gal_sect}

<!-- 商城放最後：衛教是主體，遊戲是其中一種學習方式。
     順序與上方「這個網站怎麼用」的方塊一致，避免導航與陳列互相矛盾。 -->
<h2 class="sect" id="play">從免費遊戲學習</h2>
<div class="sd">邊玩邊收集護腎知識卡與貓咪貼圖——不收費、沒有金流，唯一會出貨的是護腎知識</div>
<a class="gamebtn" href="/shop.html">
  <img src="/logo-white.png" alt="" aria-hidden="true"{logo_dims}>
  <span class="cap">護腎知識卡片收集遊戲</span>
</a>
"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/",
        "author": author_ld(),
    }
    # 首頁的分享圖示放兩處：「這個網站怎麼用」下方，以及免責聲明下方。
    # 腳本只輸出一次，掛在後者——它在文件的後面，執行時兩組都已經存在。
    return page(title, desc, "", body, jsonld,
                after_disclaimer=share_buttons("", HOME_SHARE_TITLE, top=True)
                + share_script() + search_script())


def search_script() -> str:
    """首頁全站搜尋。只在首頁輸出。

    索引在「第一次聚焦搜尋框」時才 fetch，首頁初次開啟不會為了搜尋多下載東西。
    中文用子字串比對而不是斷詞：資料量不大，子字串在中文上反而不會有斷錯詞
    搜不到的問題，也省掉一個第三方相依。
    """
    return """
<script>
(function(){
  var box = document.getElementById('sq'), out = document.getElementById('sres');
  if (!box || !out) return;
  var idx = null, loading = null;

  function load(){
    if (idx) return Promise.resolve(idx);
    if (!loading) loading = fetch('/search_index.json')
      .then(function(r){ return r.json(); })
      .then(function(d){ idx = d; return d; })
      .catch(function(){ idx = []; return idx; });
    return loading;
  }
  box.addEventListener('focus', load, {once: true});

  function esc(s){ return s.replace(/[&<>"]/g, function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

  /* 摘要從命中的位置往前後各取一段，讓使用者看得到關鍵字的上下文，
     而不是永遠顯示開頭那句 */
  function snippet(text, q){
    var i = text.toLowerCase().indexOf(q);
    if (i < 0) return esc(text.slice(0, 70));
    var from = Math.max(0, i - 24), to = Math.min(text.length, i + q.length + 46);
    return (from ? '…' : '') + esc(text.slice(from, i))
         + '<mark>' + esc(text.slice(i, i + q.length)) + '</mark>'
         + esc(text.slice(i + q.length, to)) + (to < text.length ? '…' : '');
  }

  function run(){
    var q = box.value.trim().toLowerCase();
    if (q.length < 1) { out.hidden = true; out.innerHTML = ''; return; }
    load().then(function(list){
      var hits = [];
      for (var i = 0; i < list.length && hits.length < 400; i++){
        var e = list[i];
        var ti = e.t.toLowerCase().indexOf(q);
        var bi = ti >= 0 ? -1 : (e.b || '').toLowerCase().indexOf(q);
        if (ti < 0 && bi < 0) continue;
        /* 標題命中排前面：標題就是主題，內文命中可能只是順帶提到。
           圖卡再往後 40：它是配圖，同樣命中時文字內容才是完整的答案。 */
        var rank = (ti >= 0 ? ti : 1000 + bi) + (e.g ? 40 : 0);
        hits.push({e: e, rank: rank});
      }
      hits.sort(function(a, b){ return a.rank - b.rank; });
      if (!hits.length){
        out.innerHTML = '<div class="snone">找不到「' + esc(box.value.trim())
                      + '」。可以試試更短的關鍵字，例如「蛋白尿」而不是整句話。</div>';
        out.hidden = false; return;
      }
      var html = '';
      for (var j = 0; j < hits.length && j < 12; j++){
        var e = hits[j].e;
        html += '<a href="' + e.u + '"><div class="st">' + esc(e.t)
              + '<span class="sc">' + esc(e.c) + '</span></div>'
              + '<div class="sx">' + snippet(e.b || '', q) + '</div></a>';
      }
      if (hits.length > 12){
        html += '<div class="snone">另有 ' + (hits.length - 12)
              + ' 筆，輸入更完整的關鍵字可以縮小範圍。</div>';
      }
      out.innerHTML = html; out.hidden = false;
    });
  }

  var timer = null;
  box.addEventListener('input', function(){
    clearTimeout(timer); timer = setTimeout(run, 120);   // 逐字比對會卡，稍等一下再跑
  });
  box.addEventListener('keydown', function(e){
    if (e.key === 'Escape'){ box.value = ''; out.hidden = true; }
    if (e.key === 'Enter'){
      var first = out.querySelector('a');
      if (first) location.href = first.getAttribute('href');
    }
  });
  /* 點到結果以外的地方就收起來，但不要在點結果連結時收掉 */
  document.addEventListener('click', function(e){
    if (!out.contains(e.target) && e.target !== box) out.hidden = true;
  });
})();
</script>
"""


# 醫師介紹要條列的資歷。第一項是最強的權威訊號，刻意排在最前面。
# 資歷分組陳列。原本是十項平鋪的清單，讀者要自己分辨哪一項是現職、哪一項是
# 執照。分成「現職／學歷與經歷／專科執照與認證／學會與委員會」四組之後，
# 一眼就看得出資歷的組成——這是醫師個人網站的通行寫法，對 YMYL 的
# E-E-A-T 判定也比一長串未分類的字串清楚。
#
# 內容完全沿用原本那十項，沒有新增任何宣稱；True 代表加粗顯示的重點項目。
CREDENTIAL_GROUPS = [
    ("現職", [
        ("郭綜合醫院腎臟內科主治醫師", True),
        ("台灣慢性腎臟病臨床診療指引編撰委員", True),
    ]),
    ("學歷與經歷", [
        ("國立成功大學醫學系畢業", False),
        ("前成大醫院主治醫師", False),
    ]),
    ("專科執照與認證", [
        ("腎臟科專科醫師", True),
        ("內科專科醫師", False),
        ("戒菸治療醫師", False),
        ("糖尿病共照網醫師", False),
    ]),
    ("學會與委員會", [
        ("台灣腎臟醫學會會員", False),
        ("美國腎臟醫學會會員", False),
    ]),
]

CHECK_SVG = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">'
             '<circle cx="12" cy="12" r="11" fill="currentColor" opacity=".16"/>'
             '<path d="M7 12.4l3.2 3.2L17 8.8" stroke="currentColor" stroke-width="2.4" '
             'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def img_size(p: Path) -> tuple[int, int] | None:
    """讀出 PNG/JPEG 的原始尺寸，寫進 width/height 屬性避免圖片載入時版面跳動。"""
    try:
        b = p.read_bytes()
    except OSError:
        return None
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        import struct
        w, h = struct.unpack(">II", b[16:24])
        return w, h
    if b[:2] == b"\xff\xd8":
        i = 2
        while i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h = int.from_bytes(b[i + 5:i + 7], "big")
                w = int.from_bytes(b[i + 7:i + 9], "big")
                return w, h
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    return None


def find_doctor_photo() -> tuple[str, int, int] | None:
    """找醫師照片。放進 repo 根目錄命名為 doctor.jpg／doctor.png 即會自動採用；
    沒有檔案時醫師介紹會退成純資歷條列，頁面不會壞掉。"""
    for name in ("doctor.jpg", "doctor.jpeg", "doctor.png", "doctor.webp"):
        p = ROOT / name
        if p.exists():
            wh = img_size(p)
            return (name, wh[0], wh[1]) if wh else (name, 0, 0)
    return None


GALLERY_MANIFEST = ROOT / "gallery" / "manifest.json"


def load_gallery() -> list[dict]:
    if not GALLERY_MANIFEST.exists():
        return []
    try:
        return json.loads(GALLERY_MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _gal_card(it: dict) -> str:
    src = (f'<span class="src">{it["date"]}　·　'
           f'<a href="{esc(it["permalink"])}" target="_blank" rel="noopener">原始貼文 →</a>'
           f"</span>" if it.get("permalink") else f'<span class="src">{it["date"]}</span>')
    day = f'<span class="day">Day {it["day"]}</span>' if it.get("day") else ""
    # 每張給一個錨點，全站搜尋才能直接跳到那一張而不是只到整頁。
    # 用 manifest 的 id（含底線與數字），前面加 g- 以免以數字開頭。
    return (f'<div class="galcard" id="g-{esc(it["id"])}">'
            f'<a class="shot" href="/{it["full"]}" target="_blank" rel="noopener">'
            f'<img src="/{it["thumb"]}" alt="{esc(it["cap"])}" loading="lazy" '
            f'width="360" height="360"></a>'
            f'<div><h3>{day}{esc(it["cap"])}</h3>'
            f'<p class="post">{esc(it.get("text", ""))}</p>{src}</div>'
            f"</div>")


def build_gallery(items: list[dict]) -> list[tuple[str, str]]:
    """衛教圖卡：一頁總覽 + 每個主題各一頁。

    刻意拆成多頁而不是全部塞一頁——95 張卡片加上完整貼文約兩萬七千字，
    單頁會高達兩萬多像素，讀者滑不到底，八個主題混在一起也讓每頁的主題失焦。
    拆開後每頁三千多字、聚焦單一主題，對閱讀和搜尋都比較好。

    另外刻意不寫 JavaScript 燈箱——縮圖直接連到大圖檔，
    搜尋引擎抓得到、沒有 JS 也能用。
    """
    if not items:
        return []

    # 系列的中繼資料由 import_gallery.py 產生，這裡直接讀，避免兩邊各維護一份
    sp = ROOT / "gallery" / "series.json"
    try:
        series = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else []
    except json.JSONDecodeError:
        series = []
    by_series: dict[str, list[dict]] = {}
    for it in items:
        by_series.setdefault(it.get("series", "其他"), []).append(it)

    out: list[tuple[str, str]] = []

    for s in series:
        name, slug = s["name"], s["slug"]
        group = by_series.get(name, [])
        if not group:
            continue
        path = f"articles/gallery-{slug}.html"
        # Day 區間沒有人拿來搜尋，放標題只會把標題推過截斷長度，移到描述裡。
        rng = f"（{s['day_range']}）" if s.get("day_range") else ""
        title = f"{name}：{len(group)} 張衛教圖卡｜{SITE_NAME}"
        heads = "、".join(it["cap"] for it in group[:3])
        desc = (f"{AUTHOR_NAME}醫師的「{name}」系列{rng}共 {len(group)} 張衛教圖解，"
                f"內容包含：{heads} 等。")[:150]

        others = "".join(
            f'<a href="/articles/gallery-{o["slug"]}.html">'
            f'<div class="t">{esc(o["name"])}（{o["count"]}）</div>'
            f'<div class="d">{esc(o.get("intro", "")[:44])}…</div></a>'
            for o in series if o["name"] != name)

        body = f"""
<h1>{esc(name)}</h1>
<p class="lede">{esc(s.get("intro", ""))}以下 {len(group)} 張圖卡原本發表在社群上，
依 Day 順序整理，並附上每張圖當初的完整說明文字。點圖片可看大圖。</p>
<p class="meta">作者：<a href="/about.html">{esc(AUTHOR_NAME)}</a>（{esc(AUTHOR_TITLE)}）
　·　共 {len(group)} 張{rng}　·　更新於 {TODAY}</p>
<div class="galnav"><a href="/articles/gallery.html">← 全部系列</a>
<a href="/articles/">依主題閱讀 →</a></div>
{''.join(_gal_card(it) for it in group)}
<h2 class="backlink">其他系列</h2>
<div class="cats">{others}</div>
"""
        jsonld = {
            "@context": "https://schema.org", "@type": "ImageGallery",
            "name": name, "description": desc, "inLanguage": "zh-Hant",
            "url": f"{BASE_URL}/{path}", "dateModified": TODAY,
            "numberOfItems": len(group),
            "author": author_ld(),
        }
        out.append((path, page(title, desc, path, body, jsonld)))

    # 總覽頁：每個主題一張卡片，配四張縮圖當預覽
    path = "articles/gallery.html"
    title = f"衛教圖卡總覽：{len(items)} 張腎臟與三高圖解｜{SITE_NAME}"
    desc = (f"{AUTHOR_NAME}醫師整理的 {len(items)} 張腎臟與三高衛教圖卡，"
            "依血壓、血糖、血脂、飲食、用藥安全、檢查數值等八個主題分類。")

    blocks = []
    for s in series:
        group = by_series.get(s["name"], [])
        if not group:
            continue
        prev = "".join(
            f'<img src="/{it["thumb"]}" alt="{esc(it["cap"])}" loading="lazy" '
            f'width="360" height="360">' for it in group[:4])
        rng = f'　{s["day_range"]}' if s.get("day_range") else ""
        blocks.append(
            f'<a class="galgroup" href="/articles/gallery-{s["slug"]}.html">'
            f'<div class="gg-head"><b>{esc(s["name"])}</b>'
            f'<span>{len(group)} 張{rng} →</span></div>'
            f'<div class="gg-sub">{esc(s.get("intro", ""))}</div>'
            f'<div class="gg-prev">{prev}</div></a>')

    body = f"""
<h1>衛教圖卡總覽</h1>
<p class="lede">社群上發表過的衛教圖解，依原本的系列整理收錄，每一張都附上當初的完整說明文字。
共 {len(items)} 張。</p>
<p class="meta">作者：<a href="/about.html">{esc(AUTHOR_NAME)}</a>（{esc(AUTHOR_TITLE)}）
　·　更新於 {TODAY}</p>
{''.join(blocks)}
"""
    jsonld = {
        "@context": "https://schema.org", "@type": "CollectionPage",
        "name": title, "description": desc, "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/{path}", "dateModified": TODAY,
        "author": author_ld(),
    }
    out.append((path, page(title, desc, path, body, jsonld)))
    return out


HERO_DIR = ROOT / "hero"


def hero_for(path: str):
    """長文的首頁大圖。檔名規則：hero/<slug>.jpg（slug 就是文章的檔名）。

    圖片是人工產生後放進來的，不是這支程式產生的——所以這裡只認檔案在不在，
    沒有就退回佔位塊，不會出現破圖。放一張就換一張，不必等全部到齊。
    加圖之後記得跑 bump_assets.py，hero/ 已列入雜湊來源，Service Worker
    的版本號才會跟著變，舊訪客才看得到新圖。
    """
    slug = Path(path).stem
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = HERO_DIR / (slug + ext)
        if p.exists():
            return f"hero/{slug}{ext}", img_size(p)
    return None, None


def mag_card(a: dict, cover: bool = False) -> str:
    """雜誌式的長文卡片：上圖下文。第一篇佔滿整排當封面。

    沒有圖的時候用同尺寸的漸層佔位塊，維持格線整齊——混排「有圖卡片」與
    「純文字卡片」會讓整區看起來像壞掉，寧可先放一致的佔位。
    """
    src, dims = hero_for(a["path"])
    if src:
        wh = f' width="{dims[0]}" height="{dims[1]}"' if dims else ""
        media = (f'<img src="/{src}"{wh} alt="" aria-hidden="true" '
                 f'loading="{"eager" if cover else "lazy"}" decoding="async">')
    else:
        media = f'<div class="mph" aria-hidden="true"><span>{esc(a.get("cat") or "深入文章")}</span></div>'
    kicker = esc(a.get("cat") or "深入文章")
    return (f'<a class="mcard{" cover" if cover else ""}" href="/{a["path"]}">'
            f'{media}<div class="b"><div class="k">{kicker}</div>'
            f'<div class="t">{esc(a["title"])}</div>'
            f'<div class="d">{esc(a["summary"][:88])}…</div></div></a>')


def build_about() -> str:
    """關於作者頁。

    醫療內容（YMYL）的搜尋排名高度取決於「誰寫的、憑什麼可信」。
    只在頁尾放一個作者方塊不夠，需要一頁完整說明資歷與撰寫原則，
    並讓所有文章都連過來，形成明確的權威訊號。
    """
    title = f"關於{AUTHOR_NAME}醫師與本站｜{SITE_NAME}"
    desc = (f"{AUTHOR_NAME}，腎臟科專科醫師，臨床工作以三高、慢性腎臟病與"
            "血液透析／腹膜透析為主。本頁說明本站的內容撰寫原則、資料來源，"
            "以及本站不提供個別醫療建議的立場。")

    photo = find_doctor_photo()
    if photo:
        name, w, h = photo
        dims = f' width="{w}" height="{h}"' if w else ""
        photo_html = (f'<div><img class="docphoto" src="/{name}"{dims} '
                      f'alt="{esc(AUTHOR_NAME)}醫師" loading="eager"></div>')
        grid_cls = "docintro"
    else:
        photo_html = ""
        grid_cls = "docintro nophoto"

    creds = "".join(
        f'<div class="credgrp"><h3>{esc(label)}</h3><ul class="doccred">'
        + "".join(
            f'<li class="key">{CHECK_SVG}<span>{esc(t)}</span></li>' if key
            else f'<li>{CHECK_SVG}<span>{esc(t)}</span></li>'
            for t, key in rows)
        + "</ul></div>"
        for label, rows in CREDENTIAL_GROUPS)

    body = f"""
<h1>關於{esc(AUTHOR_NAME)}醫師與本站</h1>

<div class="{grid_cls}">
{photo_html}
<div>
  <div class="docname"><small>腎臟科</small>{esc(AUTHOR_NAME)}醫師</div>
  {creds}
</div>
</div>

<h2 id="zhuan-chang">臨床專長</h2>
<p>三高（高血壓、糖尿病、高血脂）、慢性腎臟病、急性腎衰竭、血液／腹膜透析、
多囊腎、電解質異常、痛風、代謝症候群、戒菸治療。</p>

<h2 id="wei-shen-me">為什麼做這個網站</h2>
<p>在門診，我至少要花十分鐘，才能把護腎這件事跟一位病人講清楚。
一節門診四個小時，只能幫助<strong>二十四個人</strong>。</p>

<p>後來我開始在社群上寫這些事。同樣的內容發一篇文，運氣好的時候，
會有幾千、幾萬、甚至上百萬人看到——而且看完的人還會回家講給爸媽聽。
同一件事，效率差了好幾個數量級。</p>

<p>但網路也是錯誤資訊最多的地方。門診裡最讓我為難的，從來不是不願意配合的病人，
而是<strong>被錯誤資訊嚇到、或被錯誤資訊耽誤</strong>的人——
健檢報告上一個紅字，網路上查到的答案從「沒事」到「準備洗腎」都有；
而真正需要警覺的訊號，反而常被當成小毛病。</p>

<p>所以這個網站要做的不只是「讓更多人看到」，而是讓更多人看到<strong>可靠的東西</strong>：
每一則內容都寫明依據的臨床指引，不確定的地方就直說不確定，不推薦任何商品。</p>

<p>我沒有辦法在門診遇到每一個人。但如果你在拿到報告的那個晚上，
能在這裡找到一個看得懂、而且不會嚇你的答案，
知道問題在哪裡、下次回診該問什麼——那這個網站就有它存在的意義。</p>

<h2 id="yuan-ze">內容撰寫原則</h2>
<ul>
<li><strong>以國際指引與期刊文獻為依據</strong>，主要參考 KDIGO 慢性腎臟病指引、
以及腎臟醫學與內科領域的同儕審查期刊。</li>
<li><strong>不確定的就說不確定。</strong>醫學上有很多還沒有定論的問題，
這種時候會直接寫「目前證據還不夠」，而不是給一個聽起來很篤定的答案。</li>
<li><strong>不推薦任何商品。</strong>本站不接受保健食品、藥品或醫療器材的業配與贊助，
也不會在文章中推薦特定品牌。</li>
<li><strong>內容會更新。</strong>指引改版、有新的重要證據時會回頭修改舊文，
每篇文章都標示發布與更新日期。</li>
</ul>

<h2 id="bu-ti-gong">本站不提供什麼</h2>
<p>本站的內容是<strong>一般性的健康衛教</strong>，不是針對任何特定個人的診療建議。
具體而言：</p>
<ul>
<li>不提供線上診斷、不解讀個人的檢查報告</li>
<li>不提供個別的用藥建議或劑量調整</li>
<li>不回覆與個人病情有關的私訊或留言諮詢</li>
</ul>
<p>每個人的狀況都不一樣——同樣一個 eGFR 數值，在不同年齡、有沒有蛋白尿、
有沒有其他共病的人身上，意義可能完全不同。這些判斷需要完整的病史、
檢查結果與當面評估，不是任何網站能取代的。<strong>請與你的主治醫師討論。</strong></p>

<h2 id="lian-luo">聯絡方式</h2>
<p>媒體採訪、授權轉載、演講邀約，或發現內容有誤，歡迎來信：</p>
<p class="contact"><a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
<div class="warnbox">
  <b>本信箱不提供個人醫療諮詢</b>
  <p>不解讀檢查報告、不回覆病情問題、不提供用藥建議。這些判斷需要完整的病史、
  檢查結果與當面評估，請與你的主治醫師討論。</p>
  <p><strong>也請不要在信中提供你的檢查數值、病歷或其他健康資訊</strong>——
  那屬於個人資料保護法的特種個人資料，為了保護你，本站不會蒐集也不會保存。</p>
</div>
<p>本站文章歡迎在<strong>註明出處與連結原文</strong>的前提下引用。
內容如有錯誤或已被新版指引取代，請來信告知，我會更正並註明修改日期。</p>

<h2 id="she-qun">社群帳號</h2>
<p>以下是我本人經營的帳號。日常的衛教圖卡與短文會先發在社群，
完整的長文與整理過的內容放在這個網站。</p>
<p class="social sociallist">{social_links()}</p>
"""

    jsonld = {
        "@context": "https://schema.org",
        "@type": "AboutPage",
        "name": title,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/about.html",
        "dateModified": TODAY,
        # 結構化資料把資歷寫成機器讀得懂的欄位。醫療內容的可信度評估
        # 很吃「作者是誰、憑什麼」，學歷、任職與指引編撰身分都是可查證的訊號。
        # 完整版只放這一頁，其他頁用同一個 @id 指回來。
        "mainEntity": author_ld(full=True),
    }
    return page(title, desc, "about.html", body, jsonld)


# ---------------------------------------------------------------------------
# 食物查詢工具
#
# 這一頁的醫療風險比其他頁高，因此有三個刻意的設計決定：
#
# 1. 不給「能吃／不能吃」的二元答案。同一種食物對第 2 期、第 5 期與透析病人
#    的意義完全不同，二元答案必然對其中某一群人是錯的。改成顯示數值 + 分級
#    + 說明「誰該在意這一項」。
#
# 2. 蛋白質不做好壞分級。早期 CKD 常需限制蛋白質，透析病人反而要增加——方向
#    相反，做成紅綠燈一定會害到其中一群人，所以只顯示數值並加註提醒。
#
# 3. 門檻標示為「本站採用」而非醫學標準，並附資料來源與單位。
# ---------------------------------------------------------------------------

FOOD_DB = ROOT / "food_db.json"

# 每 100 公克的分級門檻，腎臟病飲食衛教常用的區間。改這裡前端就會跟著變。
FOOD_TIERS = {
    "na": {"label": "鈉", "unit": "mg", "mid": 100, "high": 400},
    "k":  {"label": "鉀", "unit": "mg", "mid": 150, "high": 250},
    "p":  {"label": "磷", "unit": "mg", "mid": 50,  "high": 150},
}

# 高鈉來源的快速入口。分組沿用〈外食減鈉指南〉裡「台灣外食的鹽藏在哪裡」那一節，
# 兩邊看到的分類一致。每個詞都實測過有結果——「番茄醬」「豆腐乳」查無，故未收錄。
FOOD_QUICK = [
    # 用「豆瓣醬」而非「豆瓣」：後者第一筆會命中「豆瓣菜」，那是蔬菜不是調味料
    ("調味料", ["醬油", "沙茶", "豆瓣醬", "味噌"]),
    ("加工肉品", ["香腸", "火腿", "培根", "肉鬆"]),
    ("火鍋料與冷凍", ["貢丸", "魚丸", "餃", "泡麵"]),
    ("醃漬與罐頭", ["醃", "滷", "酸菜", "泡菜", "罐頭"]),
    ("零食點心", ["餅乾", "洋芋片", "起司", "海苔"]),
]

FOOD_CSS_JS = r"""
<style>
/* 這一頁自己的色票。網站有深色模式（prefers-color-scheme），所以任何顏色都不能寫死
   ——寫死白底配 var(--fg) 的文字，在深色模式下會變成白底淺字，完全看不見。
   注意本站的變數是 --fg 不是 --ink。
   （.warnbox 的色票已移到共用 CSS，因為醫師簡介頁也用得到。） */
:root{
  --lo-bg:#f0f8f1; --lo-line:#bcdcc0;
  --mid-bg:#fdf7e6; --mid-line:#e8d59a;
  --hi-bg:#fdf0ee; --hi-line:#e9b4aa;
  --chip-bg:#fafafa;
}
@media (prefers-color-scheme:dark){
  :root{
    --lo-bg:#17251b; --lo-line:#2f4a35;
    --mid-bg:#2a2415; --mid-line:#5a4a1e;
    --hi-bg:#2b1a18; --hi-line:#5c302a;
    --chip-bg:#1a1712;
  }
}
.foodtool{margin:26px 0 34px}
.fsearch{display:flex;gap:10px;flex-wrap:wrap}
.fsearch input{flex:1 1 240px;min-width:0;padding:13px 15px;font-size:1.05rem;
border:2px solid var(--line);border-radius:10px;background:var(--bg);color:var(--fg)}
.fsearch input:focus{outline:none;border-color:var(--accent2)}
.fsearch select{padding:13px 12px;font-size:1rem;border:2px solid var(--line);
border-radius:10px;background:var(--bg);color:var(--fg)}
.fhint{color:var(--mut);font-size:.9rem;margin:10px 2px 0}
.fquick{margin:14px 0 4px;display:flex;flex-direction:column;gap:7px}
.qlead{color:var(--mut);font-size:.88rem;margin:0 2px 2px}
.qrow{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.qcat{font-size:.78rem;color:var(--mut);min-width:5.6em}
.qchip{font:inherit;font-size:.88rem;padding:5px 12px;border-radius:999px;
border:1px solid var(--line);background:var(--bg);color:var(--fg);cursor:pointer}
.qchip:hover{border-color:var(--accent2);color:var(--accent2)}
.qchip:focus-visible{outline:2px solid var(--accent2);outline-offset:2px}
/* 手機上不要讓分類標籤獨佔一行——那會讓整塊高到 440px，
   把搜尋結果推出畫面外。改成與按鈕同行流動。 */
@media(max-width:560px){
  .qcat{min-width:0;margin-right:2px}
  .qchip{padding:4px 10px;font-size:.85rem}
  .fquick{gap:5px}
}
.fres{margin-top:14px;display:flex;flex-direction:column;gap:10px}
.fcard{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:var(--card)}
/* 全站的 h3 是灰色次級小標（color:var(--mut)），但食物名稱是卡片主體，
   要用正文色。圖卡的 .galcard h3 也是同樣的覆寫。 */
.fcard h3{margin:0 0 3px;font-size:1.06rem;color:var(--fg)}
.fcard .fmeta{color:var(--mut);font-size:.83rem;margin:0 0 10px}
.fvals{display:flex;flex-wrap:wrap;gap:8px}
.fv{display:flex;align-items:baseline;gap:6px;padding:6px 11px;border-radius:999px;
font-size:.9rem;border:1px solid var(--line);background:var(--chip-bg);color:var(--fg)}
.fv .num{font-variant-numeric:tabular-nums;font-weight:700}
.fv .rng{font-variant-numeric:tabular-nums;font-size:.78rem;color:var(--mut)}
.fv.lo{background:var(--lo-bg);border-color:var(--lo-line)}
.fv.mid{background:var(--mid-bg);border-color:var(--mid-line)}
.fv.hi{background:var(--hi-bg);border-color:var(--hi-line)}
.fv .tag{font-size:.76rem;color:var(--mut)}
/* 全站的 th,td 是 white-space:nowrap（給分期表那種短欄位用的）。
   這張表的第三欄是長句子，必須允許換行，否則會把版面撐到 1,200px 以上。 */
.ftiers th,.ftiers td{white-space:normal;vertical-align:top}
.ftiers td:first-child,.ftiers th:first-child{white-space:nowrap}
@media(max-width:560px){ .fsearch select{flex:1 1 100%} }
</style>
<script>
const TIERS = __TIERS__;
let DB = null;

const tier = (key, v) => {
  if(v === null || v === undefined) return "";
  const t = TIERS[key];
  return v >= t.high ? "hi" : (v >= t.mid ? "mid" : "lo");
};
const tierWord = c => c === "hi" ? "偏高" : (c === "mid" ? "中等" : "偏低");

/* 數值欄是 [代表值] 或 [代表值, 最小, 最大]。同一種食物多次取樣且差異大時
   顯示範圍，而不是挑一個數字假裝很精確。 */
function card(r){
  const [name, alias, cat, samples, na, k, p, prot, kcal] = r;
  /* 括號不可省：「352.7 303–463」會讓人分不出哪個是代表值 */
  const span = v => (v.length > 1) ? ('<span class="rng">(' + v[1] + '–' + v[2] + ')</span>') : '';
  const chip = (key, v) => {
    if(!v) return "";
    const t = TIERS[key], c = tier(key, v[0]);
    return '<span class="fv ' + c + '">' + t.label +
           '<span class="num">' + v[0] + '</span>' + span(v) +
           '<span class="tag">' + t.unit + '・' + tierWord(c) + '</span></span>';
  };
  const plain = (label, v, unit) => !v ? "" :
    '<span class="fv">' + label + '<span class="num">' + v[0] + '</span>' + span(v) +
    '<span class="tag">' + unit + '</span></span>';
  const note = samples > 1 ? ('　·　' + samples + ' 次取樣') : '';
  return '<div class="fcard"><h3>' + name + '</h3>' +
         '<p class="fmeta">' + cat + (alias ? '　俗名：' + alias : '') +
         '　·　每 100 公克' + note + '</p>' +
         '<div class="fvals">' + chip("na", na) + chip("k", k) + chip("p", p) +
         plain("蛋白質", prot, "g") + plain("熱量", kcal, "kcal") + '</div></div>';
}

/* force=true 用於快速入口的按鈕：那是刻意的點擊、詞也是我們挑好的，
   不該被「輸入兩個字以上」擋住（「餃」「醃」「滷」都是單字）。
   那條限制的用意只是避免打字過程中一次算出上千筆。 */
function render(force){
  const q = document.getElementById("fq").value.trim();
  const cat = document.getElementById("fcat").value;
  const hint = document.getElementById("fhint");
  const box = document.getElementById("fres");
  if(!DB){ hint.textContent = "資料載入中…"; return; }
  if(q.length < (force ? 1 : 2) && !cat){
    box.innerHTML = "";
    hint.textContent = "共 " + DB.rows.length.toLocaleString() + " 種食物。輸入兩個字以上開始搜尋。";
    return;
  }
  let hits = DB.rows;
  if(cat) hits = hits.filter(r => r[2] === cat);
  if(q){
    hits = hits.filter(r => r[0].includes(q) || (r[1] && r[1].includes(q)));
    /* 相關度排序：完全相同的名稱最前，其次是名稱越短越通用。
       否則搜「醬油」第一筆會是「醬油西瓜子」，不是使用者想找的那瓶醬油。 */
    hits = hits.slice().sort((a, b) => {
      const ea = a[0] === q ? 0 : 1, eb = b[0] === q ? 0 : 1;
      if(ea !== eb) return ea - eb;
      const sa = a[0].startsWith(q) ? 0 : 1, sb = b[0].startsWith(q) ? 0 : 1;
      if(sa !== sb) return sa - sb;
      return a[0].length - b[0].length;
    });
  }
  /* 「查不到」多半不是打錯字，而是搜了店家現做的料理。界線是「有沒有包裝標示」：
     泡麵、水餃、醬油查得到，滷肉飯、牛肉麵查不到。講清楚界線在哪，
     比籠統說「這是食材資料庫」有用——後者會讓人連泡麵都懶得查。 */
  hint.innerHTML = hits.length
    ? ("找到 " + hits.length + " 筆")
    : '查不到「' + q + '」。資料庫收錄<b>食材、包裝與冷凍食品、調味料、飲料</b>'
      + '（泡麵、水餃、醬油、奶茶都查得到），但沒有店家現做的料理。'
      + '試著拆開查食材或調味料，例如查不到「滷肉飯」，可以查「豬肉」「醬油」。';
  box.innerHTML = hits.slice(0, 60).map(card).join("");
  if(hits.length > 60) box.insertAdjacentHTML("beforeend",
    '<p class="fhint">只顯示前 60 筆，請輸入更完整的名稱縮小範圍。</p>');
}

/* 這段是從 <head> 載入的，執行時 body 還沒解析，直接抓元素會拿到 null。
   全部等 DOMContentLoaded 之後再做。 */
function init(){
  const q = document.getElementById("fq");
  q.addEventListener("input", render);
  document.getElementById("fcat").addEventListener("change", render);
  /* 快速入口：填進搜尋框直接查。結果區就在按鈕上方，不需要捲動。 */
  document.querySelectorAll(".qchip").forEach(b => {
    b.addEventListener("click", () => {
      q.value = b.dataset.q;
      document.getElementById("fcat").value = "";
      render(true);
    });
  });
  (async () => {
    try{
      DB = await (await fetch("/food_db.json")).json();
      const sel = document.getElementById("fcat");
      DB.cats.forEach(c => {
        const o = document.createElement("option");
        o.value = c; o.textContent = c; sel.appendChild(o);
      });
      render();
    }catch(e){
      document.getElementById("fhint").textContent = "資料載入失敗，請重新整理頁面。";
    }
  })();
}
if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
</script>
"""


def build_food() -> str:
    """食物營養查詢頁。資料在建置時就轉好放進 food_db.json，
    前端只做搜尋與篩選——沒有後端，也不記錄使用者查了什麼。"""
    if not FOOD_DB.exists():
        return ""

    db = json.loads(FOOD_DB.read_text(encoding="utf-8"))
    n = len(db["rows"])

    quick_html = "".join(
        f'<div class="qrow"><span class="qcat">{esc(cat)}</span>'
        + "".join(f'<button type="button" class="qchip" data-q="{esc(w)}">{esc(w)}</button>'
                  for w in words)
        + "</div>"
        for cat, words in FOOD_QUICK)

    # 標題裡的收錄數不是搜尋詞，讓位給「蛋白質」。數量仍寫在描述與頁面內文
    title = f"腎臟病飲食查詢：食物的鈉鉀磷與蛋白質含量｜{SITE_NAME}"
    desc = (f"查詢 {n:,} 種食物的鈉、鉀、磷與蛋白質含量，資料來自衛福部食藥署"
            f"台灣食品營養成分資料庫。該注意哪一項，取決於你的腎功能分期。")

    body = f"""
<h1>腎臟病飲食查詢</h1>
<p class="lede">查詢食物的<strong>鈉、鉀、磷、蛋白質</strong>含量。這四項是腎臟病飲食最需要注意的，
但<strong>該注意哪一項，取決於你的腎功能分期</strong>——不是每個人都要限制同樣的東西。</p>

<div class="warnbox">
  <b>這個工具不會告訴你「能不能吃」</b>
  <p>因為同一種食物，對第 2 期、第 5 期、以及透析中的病人，意義完全不同。
  給一個二元答案，必然會對其中一群人是錯的。</p>
  <p>它做的是把數值攤開，並說明<strong>哪些人需要在意哪一項</strong>。
  實際的飲食計畫請與你的醫師或營養師討論。</p>
</div>

<div class="foodtool">
  <div class="fsearch">
    <input id="fq" type="search" placeholder="食物名稱，例如 香蕉、泡麵、醬油、水餃…"
           autocomplete="off" spellcheck="false" aria-label="搜尋食物">
    <select id="fcat" aria-label="依分類篩選"><option value="">全部分類</option></select>
  </div>
  <p class="fhint" id="fhint">共 {n:,} 種食物。輸入兩個字以上開始搜尋。</p>
  <!-- 結果放在快速入口之前：沒搜尋時它高度為零，按鈕自然貼在搜尋框下方；
       一搜尋結果就出現在眼睛正在看的位置，不必自動捲動（捲動會讓人失去方向）。 -->
  <div id="fres" class="fres"></div>
  <div class="fquick">
    <p class="qlead">不知道要查什麼？台灣外食的鈉主要來自這幾類——點一下直接查：</p>
    {quick_html}
  </div>
</div>

<div class="note">
  <p><b>看調味料的數字時要留意份量。</b>醬油每 100 公克含鈉四千多毫克看起來嚇人，
  但沒有人一次吃 100 公克的醬油。這類食物的重點不是單一數字，而是<strong>用量與頻率</strong>
  ——同一瓶醬油，沾著吃和淋上去的差別很大。做法見
  <a href="/articles/taiwan-eating-out-sodium.html">外食減鈉指南</a>。</p>
</div>

<h2 id="san-xiang">這四項分別是誰要注意</h2>
<div class="tw">
<table class="ftiers">
  <thead><tr><th>營養素</th><th>誰需要注意</th><th>為什麼</th></tr></thead>
  <tbody>
    <tr><td><b>鈉</b></td><td>幾乎所有人</td>
        <td>升高血壓、增加腎絲球負擔、加重蛋白尿，還會削弱降血壓藥的效果。
        詳見<a href="/articles/taiwan-eating-out-sodium.html">外食減鈉指南</a></td></tr>
    <tr><td><b>鉀</b></td><td>晚期（eGFR 低於 30）與透析患者</td>
        <td>腎功能下降時排鉀能力變差，血鉀過高可能造成心律不整，且初期沒有症狀。
        <strong>早期患者通常不需要限鉀</strong>，過度限制反而會少吃了蔬果</td></tr>
    <tr><td><b>磷</b></td><td>中晚期（eGFR 低於 45）與透析患者</td>
        <td>磷排不掉會影響骨骼與血管。加工食品的「磷酸鹽添加物」吸收率遠高於
        天然食物中的磷，是最該優先避開的來源</td></tr>
    <tr><td><b>蛋白質</b></td><td>幾乎所有人</td>
        <td>慢性腎臟病常需要<strong>限制</strong>，透析患者反而需要<strong>增加</strong>。
        正因為方向相反，本站不對蛋白質做高低分級，只顯示數值——你的目標值
        請直接問你的醫師或營養師</td></tr>
  </tbody>
</table>
</div>

<div class="note">
  <p><b>蛋白質為什麼不做分級？</b>因為方向是相反的：<strong>慢性腎臟病常需要限制蛋白質，
  透析患者反而需要增加</strong>。做成紅綠燈一定會害到其中一群人，所以這裡只顯示數值。
  你的蛋白質目標請直接問你的醫師或營養師。</p>
</div>

<h2 id="lai-yuan">資料來源與限制</h2>
<ul>
<li>資料來自<strong>衛生福利部食品藥物管理署「台灣食品營養成分資料庫」</strong>
（<a href="{db['source_url']}" rel="noopener" target="_blank">政府資料開放平臺</a>，
{db['licence']}），共 {n:,} 種食物</li>
<li>所有數值為<strong>{db['unit']}</strong>的含量</li>
<li><strong>烹調方式會大幅改變結果</strong>：水煮會讓鉀溶進水裡，所以「先燙過再炒」
是常見的降鉀做法；反之滷、醃、加工會大幅增加鈉</li>
<li><strong>收錄範圍</strong>：食材（蔬果、肉類、魚貝、穀物）、包裝與冷凍食品、
糕餅點心、調味料、飲料。泡麵、水餃、飯糰、醬油、沙茶、奶茶都查得到。
<strong>但沒有店家現做的料理</strong>——查不到滷肉飯、牛肉麵、鹽酥雞。
界線大致是「有沒有包裝與營養標示」</li>
<li>同一種食物多次取樣且差異較大時，會同時顯示<strong>代表值與範圍</strong>，
不挑單一數字假裝精確</li>
</ul>
"""

    extra = FOOD_CSS_JS.replace("__TIERS__", json.dumps(FOOD_TIERS, ensure_ascii=False))
    jsonld = {
        "@context": "https://schema.org",
        "@type": "MedicalWebPage",
        "name": title,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/food.html",
        "dateModified": TODAY,
        "author": author_ld(),
        **reviewed_ld(),
        "citation": {"@type": "Dataset", "name": db["source"], "url": db["source_url"]},
    }
    return page(title, desc, "food.html", body, jsonld, extra_head=extra)


# ---------------------------------------------------------------------------
# 腎功能計算工具
#
# 這一頁的風險比食物查詢更高：它輸出的是可以直接影響病人決策的數字。
# 幾個刻意的設計決定：
#
# 1. 輸入的是使用者已經擁有的檢驗值，不做任何診斷推論。
# 2. 有填 cystatin C 就自動改用 creatinine-cystatin C 式，並明確標示
#    「本次使用哪一條公式」——兩式結果可能差很多，不說清楚會誤導。
# 3. KFRE 只在 eGFR 落在其驗證範圍（G3–G5）且有 UACR 時才顯示。
#    超出範圍給出的數字沒有意義，寧可不顯示也不要給假的精確度。
# 4. 風險以區間與文字描述呈現，不只給一個裸數字。
#
# 公式來源：
#   CKD-EPI 2021 creatinine 與 creatinine-cystatin C
#     Inker LA et al. N Engl J Med 2021;385:1737-1749
#     係數已對照 National Kidney Foundation 公布版本
#   KFRE 4-variable：Tangri N et al.
#     ⚠ 係數與基線存活率待作者確認後才可發布
# ---------------------------------------------------------------------------

CALC_PUBLISHED = True

CALC_CSS_JS = r"""
<style>
/* 開放使用的聲明。語氣是正面的邀請，所以用主色細邊而不是警語的橘色，
   視覺份量刻意低於下方的警語方塊。 */
.opencall{border-left:3px solid var(--accent);background:var(--card);
padding:13px 16px;border-radius:0 8px 8px 0;margin:20px 0}
.opencall p{margin:0;font-size:.95rem;line-height:1.75}
.calcwrap{margin:24px 0 8px}
.cform{display:grid;gap:12px;grid-template-columns:1fr 1fr;
background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.cfield{display:flex;flex-direction:column;gap:5px;min-width:0}
.cfield.wide{grid-column:1 / -1}
.cfield label{font-size:13px;color:var(--mut);font-weight:500}
.cfield label b{color:var(--fg);font-weight:700}
.cfield .unit{font-size:11.5px;color:var(--mut)}
.cfield input,.cfield select{padding:11px 12px;font-size:1.02rem;border:2px solid var(--line);
border-radius:9px;background:var(--bg);color:var(--fg);width:100%}
.cfield input:focus,.cfield select:focus{outline:none;border-color:var(--accent2)}
.cfield .hint{font-size:11.5px;color:var(--mut);line-height:1.5}
.cbtns{grid-column:1 / -1;display:flex;gap:10px;flex-wrap:wrap}
.cbtn{font:inherit;font-size:1rem;font-weight:700;padding:11px 22px;border-radius:9px;
border:1px solid var(--accent);background:var(--accent);color:var(--bg);cursor:pointer}
.cbtn.ghost{background:transparent;color:var(--mut);border-color:var(--line);font-weight:500}
.cbtn:focus-visible{outline:2px solid var(--accent2);outline-offset:2px}
.cres{margin-top:16px;display:none;flex-direction:column;gap:12px}
.cres.on{display:flex}
.rbox{border:1px solid var(--line);border-radius:12px;padding:16px 18px;background:var(--card)}
.rbox .rlabel{font-size:12.5px;color:var(--mut);letter-spacing:.04em}
.rbox .rval{font-size:2.1rem;font-weight:800;line-height:1.25;
font-variant-numeric:tabular-nums;margin:2px 0 4px}
.rbox .rsub{font-size:13.5px;color:var(--mut);line-height:1.6}
.rbox .rformula{font-size:12px;color:var(--mut);margin-top:9px;
padding-top:9px;border-top:1px dashed var(--line)}
.stage{display:inline-block;padding:3px 11px;border-radius:999px;font-size:13px;
font-weight:700;border:1px solid currentColor;margin-left:8px;vertical-align:middle}
.s-g1,.s-g2{color:var(--ok,#2f7d4f)}
.s-g3a,.s-g3b{color:var(--warnc,#9a6207)}
.s-g4,.s-g5{color:var(--bad,#a33)}
.cnote{font-size:13px;color:var(--mut);line-height:1.7;margin-top:4px}
.cerr{color:#b03a2e;font-size:13.5px;margin-top:8px}
@media(prefers-color-scheme:dark){
  .s-g1,.s-g2{color:#7fd6a0}
  .s-g3a,.s-g3b{color:#e0b25c}
  .s-g4,.s-g5{color:#e88a80}
  .cerr{color:#e88a80}
}
@media(max-width:560px){ .cform{grid-template-columns:1fr} }
</style>
<script>
/* ── CKD-EPI 2021（Inker LA et al. NEJM 2021）───────────────────────
   兩式都不含人種係數。Scr 單位 mg/dL，cystatin C 單位 mg/L。 */
function ckdEpiCr(scr, age, female){
  const k = female ? 0.7 : 0.9;
  const a = female ? -0.241 : -0.302;
  const r = scr / k;
  return 142 * Math.pow(Math.min(r,1), a) * Math.pow(Math.max(r,1), -1.200)
       * Math.pow(0.9938, age) * (female ? 1.012 : 1);
}
function ckdEpiCrCys(scr, cys, age, female){
  const k = female ? 0.7 : 0.9;
  const a = female ? -0.219 : -0.144;
  const r = scr / k, c = cys / 0.8;
  return 135 * Math.pow(Math.min(r,1), a) * Math.pow(Math.max(r,1), -0.544)
       * Math.pow(Math.min(c,1), -0.323) * Math.pow(Math.max(c,1), -0.778)
       * Math.pow(0.9961, age) * (female ? 0.963 : 1);
}
function stageOf(e){
  if(e >= 90) return ["G1","正常或偏高"];
  if(e >= 60) return ["G2","輕度下降"];
  if(e >= 45) return ["G3a","輕到中度下降"];
  if(e >= 30) return ["G3b","中到重度下降"];
  if(e >= 15) return ["G4","重度下降"];
  return ["G5","腎衰竭"];
}

/* ── KFRE 4 變項（Tangri N et al. JAMA 2011;305:1553 / JAMA 2016;315:164）──
   係數與基線存活率取自官方計算機 kidneyfailurerisk.com 的實作，
   ACR 以 mg/g 代入（官方在 mg/g 時的換算係數為 1）。
   台灣屬非北美校正。 */
const KFRE_READY = true;
const KFRE_B = {age: -0.2201, male: 0.2467, egfr: -0.5567, acr: 0.4510};
const KFRE_M = {age: 7.036, male: 0.5642, egfr: 7.222, acr: 5.137};
const KFRE_S0 = {
  na:    {y2: 0.9750, y5: 0.9240},
  nonna: {y2: 0.9832, y5: 0.9365}
};
function kfre(age, male, egfr, acr, region){
  const b = KFRE_B, m = KFRE_M;
  const xb = b.age*(age/10 - m.age) + b.male*((male?1:0) - m.male)
           + b.egfr*(egfr/5 - m.egfr) + b.acr*(Math.log(acr) - m.acr);
  const s = KFRE_S0[region] || KFRE_S0.nonna;
  return {y2: 1 - Math.pow(s.y2, Math.exp(xb)),
          y5: 1 - Math.pow(s.y5, Math.exp(xb))};
}

function calcInit(){
  const $ = id => document.getElementById(id);
  const num = id => { const v = parseFloat($(id).value); return isFinite(v) ? v : null; };

  function run(){
    const age = num("cAge"), scr = num("cScr"), cys = num("cCys"), acr = num("cAcr");
    const female = $("cSex").value === "f";
    const err = $("cErr"); err.textContent = "";

    if(age === null || scr === null){
      err.textContent = "請至少填入年齡與血清肌酸酐。"; return;
    }
    if(age < 18 || age > 110){ err.textContent = "這些公式適用於 18 歲以上的成人。"; return; }
    if(scr <= 0 || scr > 25){ err.textContent = "血清肌酸酐的數值看起來不合理，請確認單位是 mg/dL。"; return; }
    if(cys !== null && (cys <= 0 || cys > 12)){
      err.textContent = "胱抑素 C 的數值看起來不合理，請確認單位是 mg/L。"; return; }

    const useCys = cys !== null;
    const e = useCys ? ckdEpiCrCys(scr, cys, age, female) : ckdEpiCr(scr, age, female);
    const [sg, sdesc] = stageOf(e);

    $("rEgfr").innerHTML = e.toFixed(1) +
      '<span class="stage s-' + sg.toLowerCase() + '">' + sg + '</span>';
    $("rEgfrSub").textContent = sdesc + "　單位 mL/min/1.73m²";
    $("rFormula").textContent = useCys
      ? "使用公式：CKD-EPI 2021 creatinine–cystatin C（因為你填了胱抑素 C）"
      : "使用公式：CKD-EPI 2021 creatinine";

    /* 只單獨顯示肌酸酐版，方便對照兩式差異 */
    const cmp = $("rCompare");
    if(useCys){
      const only = ckdEpiCr(scr, age, female);
      cmp.style.display = "";
      cmp.textContent = "只用肌酸酐計算會是 " + only.toFixed(1) +
        "，差 " + (e - only >= 0 ? "+" : "") + (e - only).toFixed(1) + "。";
    } else cmp.style.display = "none";

    /* KFRE */
    const kb = $("rKfre");
    if(!KFRE_READY){
      kb.style.display = "";
      kb.innerHTML = '<div class="rlabel">腎衰竭風險（KFRE）</div>' +
        '<div class="rsub">此區塊的公式係數尚在確認中，暫未開放。</div>';
    } else if(acr === null){
      kb.style.display = "";
      kb.innerHTML = '<div class="rlabel">腎衰竭風險（KFRE）</div>' +
        '<div class="rsub">需要尿液白蛋白／肌酸酐比值（UACR）才能計算。</div>';
    } else if(e >= 60 || e < 10){
      kb.style.display = "";
      kb.innerHTML = '<div class="rlabel">腎衰竭風險（KFRE）</div>' +
        '<div class="rsub">KFRE 的驗證範圍是慢性腎臟病第 3 到第 5 期' +
        '（eGFR 約 10–59）。你的 eGFR 為 ' + e.toFixed(1) +
        '，超出這個範圍，算出來的數字沒有意義，因此不顯示。</div>';
    } else {
      const r = kfre(age, !female, e, acr, $("cRegion").value);
      kb.style.display = "";
      kb.innerHTML = '<div class="rlabel">腎衰竭風險（KFRE 4 變項）</div>' +
        '<div class="rval">' + (r.y5*100).toFixed(1) + '%</div>' +
        '<div class="rsub">五年內進展到需要透析或移植的估計風險；' +
        '兩年風險約 ' + (r.y2*100).toFixed(1) + '%。</div>' +
        '<div class="rformula">這是族群層級的統計估計，不是個人的預言。' +
        '實際結果取決於血壓、血糖、蛋白尿是否控制得好，以及有沒有規則追蹤。</div>';
    }
    $("cRes").classList.add("on");
  }

  $("cRun").addEventListener("click", run);
  $("cClear").addEventListener("click", () => {
    ["cAge","cScr","cCys","cAcr"].forEach(i => document.getElementById(i).value = "");
    $("cRes").classList.remove("on"); $("cErr").textContent = "";
  });
  document.querySelectorAll(".cform input").forEach(el => {
    el.addEventListener("keydown", e => { if(e.key === "Enter") run(); });
  });
}
if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", calcInit);
else calcInit();
</script>
"""


def build_calc() -> str:
    """腎功能計算工具。輸入的是使用者已經有的檢驗值，不做診斷。"""
    title = f"腎功能計算：eGFR 與腎衰竭風險｜{SITE_NAME}"
    desc = ("以 CKD-EPI 2021 公式計算 eGFR（可加入胱抑素 C），並依 KFRE 估算"
            "慢性腎臟病進展到腎衰竭的風險。輸入你報告上已有的數值即可。")

    body = """
<h1>腎功能計算</h1>
<p class="lede">腎功能計算採用最新的 <strong>2021 CKD-EPI eGFR</strong> 公式。
健身族群或肌少症族群，還可以使用加入胱抑素 C 的進階版
（<strong>2021 CKD-EPI eGFRcr-cys</strong>）——比起傳統的計算方法誤差更小、更準確。</p>

<p class="lede">洗腎風險則使用 <strong>KFRE</strong> 公式，計算未來兩年與五年的腎衰竭風險。</p>

<div class="warnbox">
  <b>重要提醒</b>
  <p>本計算機<strong>不做診斷</strong>，也不會知道你的病史——它只是幫你把數字換算成
  比較好理解的形式。若有任何疑問，請跟你的主治醫師討論喔。</p>
</div>

<div class="calcwrap">
<div class="cform">
  <div class="cfield">
    <label for="cAge"><b>年齡</b> <span class="unit">歲</span></label>
    <input id="cAge" type="number" inputmode="numeric" min="18" max="110" placeholder="例如 55">
  </div>
  <div class="cfield">
    <label for="cSex"><b>生理性別</b></label>
    <select id="cSex"><option value="m">男性</option><option value="f">女性</option></select>
  </div>
  <div class="cfield">
    <label for="cScr"><b>血清肌酸酐</b> <span class="unit">mg/dL</span></label>
    <input id="cScr" type="number" inputmode="decimal" step="0.01" min="0.1" placeholder="例如 1.20">
    <span class="hint">報告上寫 Creatinine 或 Cr</span>
  </div>
  <div class="cfield">
    <label for="cCys"><b>胱抑素 C</b> <span class="unit">mg/L・可不填</span></label>
    <input id="cCys" type="number" inputmode="decimal" step="0.01" min="0.1" placeholder="例如 1.10">
    <span class="hint">填了就會自動改用較準確的合併公式</span>
  </div>
  <div class="cfield">
    <label for="cAcr"><b>尿液白蛋白／肌酸酐比值</b> <span class="unit">mg/g・可不填</span></label>
    <input id="cAcr" type="number" inputmode="decimal" step="1" min="0.1" placeholder="例如 120">
    <span class="hint">報告上寫 UACR 或 ACR</span>
  </div>
  <div class="cfield">
    <label for="cRegion"><b>KFRE 校正區域</b></label>
    <select id="cRegion">
      <option value="nonna">北美以外</option>
      <option value="na">北美</option>
    </select>
  </div>
  <div class="cbtns">
    <button id="cRun" class="cbtn" type="button">計算</button>
    <button id="cClear" class="cbtn ghost" type="button">清除</button>
  </div>
  <div class="cfield wide"><div class="cerr" id="cErr"></div></div>
</div>

<div class="cres" id="cRes">
  <div class="rbox">
    <div class="rlabel">估算腎絲球過濾率</div>
    <div class="rval" id="rEgfr">—</div>
    <div class="rsub" id="rEgfrSub"></div>
    <div class="rsub" id="rCompare" style="display:none"></div>
    <div class="rformula" id="rFormula"></div>
  </div>
  <div class="rbox" id="rKfre" style="display:none"></div>
</div>
</div>

<div class="opencall">
  <p>歡迎<strong>醫療同業自由使用</strong>本計算機，協助臨床診治病患，
  共同守護民眾的腎臟健康。<strong>本計算機永不收費。</strong></p>
</div>

<h2 id="gongshi">用的是哪些公式</h2>
<div class="tw">
<table>
  <thead><tr><th>公式</th><th>用途</th><th>來源</th></tr></thead>
  <tbody>
    <tr><td><b>CKD-EPI 2021<br>creatinine</b></td>
        <td>只用肌酸酐估算 eGFR。不含人種係數</td>
        <td>Inker LA et al. <i>N Engl J Med</i> 2021;385:1737-1749</td></tr>
    <tr><td><b>CKD-EPI 2021<br>creatinine–cystatin C</b></td>
        <td>同時使用肌酸酐與胱抑素 C，準確度較高。填了胱抑素 C 就自動改用這一式</td>
        <td>同上</td></tr>
    <tr><td><b>KFRE</b><br>（4 變項）</td>
        <td>以年齡、性別、eGFR、UACR 估算慢性腎臟病第 3–5 期患者兩年與五年內進展到腎衰竭的風險。
        台灣採<strong>非北美校正</strong></td>
        <td>Tangri N et al. <i>JAMA</i> 2011;305(15):1553-1559<br>
        Tangri N, Grams ME, Levey AS, et al. <i>JAMA</i> 2016;315(2):164-174<br>
        係數與基線存活率對照官方計算機
        <a href="https://kidneyfailurerisk.com" rel="noopener" target="_blank">kidneyfailurerisk.com</a></td></tr>
  </tbody>
</table>
</div>

<h2 id="xianzhi">限制與注意事項</h2>
<ul>
<li><strong>eGFR 是估算不是實測。</strong>肌肉量高（重訓族）會低估腎功能、肌肉量低（長者、肌少症）會高估；
抽血前劇烈運動、大量肉類、脫水或某些藥物都會影響。詳見
<a href="/articles/creatinine-high-what-to-do.html">肌酸酐偏高怎麼辦</a></li>
<li><strong>單次數值不能診斷。</strong>慢性腎臟病的定義要求異常持續超過三個月，
看的是趨勢而不是單點</li>
<li><strong>同一個數字，不同人意義不同。</strong>同樣的 eGFR，在不同年齡、
有沒有蛋白尿、有沒有其他共病的人身上，代表的風險完全不同</li>
<li><strong>eGFR 正常不代表腎臟沒事。</strong>腎臟的儲備能力會讓剩餘腎元代償，
在腎元已大量流失時數值仍可能正常。真正可能提早發現的是尿液白蛋白，詳見
<a href="/articles/egfr-meaning-ckd-stages.html">eGFR 60 是什麼意思</a></li>
<li><strong>KFRE 有適用範圍。</strong>它在慢性腎臟病第 3 到第 5 期（eGFR 約 10–59）
的族群中驗證，超出範圍的估計沒有意義，本工具在那種情況下不會顯示結果</li>
<li>本工具不會保存或傳送你輸入的任何數值，計算完全在你的瀏覽器內完成</li>
</ul>
"""

    jsonld = {
        "@context": "https://schema.org",
        "@type": "MedicalWebPage",
        "name": title,
        "description": desc,
        "inLanguage": "zh-Hant",
        "url": f"{BASE_URL}/calc.html",
        "dateModified": TODAY,
        "author": author_ld(),
        **reviewed_ld(),
    }
    return page(title, desc, "calc.html", body, jsonld, extra_head=CALC_CSS_JS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    args = ap.parse_args()

    data = json.loads((ROOT / "knowledge_export.json").read_text(encoding="utf-8"))
    by_cat: dict[str, list[dict]] = {}
    for it in data:
        by_cat.setdefault(it["cat"], []).append(it)
    by_cat = {c: by_cat[c] for c in CAT_SLUG if c in by_cat}

    OUT.mkdir(exist_ok=True)
    written: list[str] = []

    # 長文先產生，分類頁才知道要把哪幾篇列為「深入閱讀」
    md_pages = build_markdown_articles()
    for a in md_pages:
        (ROOT / a["path"]).write_text(a["html"], encoding="utf-8")
        written.append(a["path"])
        faq = f"，FAQ {a['faq_count']} 題" if a["faq_count"] else ""
        print(f"  {a['path']}　(長文，分類：{a['cat'] or '未指定'}{faq})")

    for cat, items in by_cat.items():
        path, htm, _t = build_category(cat, items, md_pages)
        (ROOT / path).write_text(htm, encoding="utf-8")
        written.append(path)
        print(f"  {path}　({len(items)} 則，約 {sum(len(i['body']) for i in items):,} 字)")

    gallery_items = load_gallery()
    for gpath, ghtml in build_gallery(gallery_items):
        (ROOT / gpath).write_text(ghtml, encoding="utf-8")
        written.append(gpath)
        print(f"  {gpath}")

    idx_path, idx_html = build_index(by_cat, md_pages,
                                     len(gallery_items))
    (ROOT / idx_path).write_text(idx_html, encoding="utf-8")
    written.insert(0, idx_path)
    print(f"  {idx_path}")

    (ROOT / "about.html").write_text(build_about(), encoding="utf-8")
    print("  about.html　(關於作者，E-E-A-T 權威訊號)")

    (ROOT / "index.html").write_text(
        build_home(by_cat, md_pages, len(gallery_items)), encoding="utf-8")
    print("  index.html　(網站首頁，衛教為主 + 商城大按鈕)")

    food_html = build_food()
    if food_html:
        (ROOT / "food.html").write_text(food_html, encoding="utf-8")
        print("  food.html　(食物營養查詢工具)")

    (ROOT / "calc.html").write_text(build_calc(), encoding="utf-8")
    print(f"  calc.html　(腎功能計算工具{'' if CALC_PUBLISHED else '，未發布'})")

    # sitemap：讓搜尋引擎一次拿到所有網址
    urls = ["", "articles/", "about.html", "shop.html"] + (
        ["food.html"] if food_html else []) + (
        ["calc.html"] if CALC_PUBLISHED else []) + [
        p for p in written if not p.endswith("index.html")]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemap.org/schemas/sitemap/0.9">'.replace(
              "www.sitemap.org", "www.sitemaps.org")]
    for u in dict.fromkeys(urls):
        pri = "1.0" if u == "" else ("0.9" if u == "articles/" else "0.8")
        sm.append(f"  <url><loc>{BASE_URL}/{u}</loc><lastmod>{TODAY}</lastmod>"
                  f"<changefreq>monthly</changefreq><priority>{pri}</priority></url>")
    sm.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    print(f"  sitemap.xml　({len(urls)} 個網址)")

    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")
    print("  robots.txt")

    n_idx = build_search_index(data, md_pages, gallery_items)
    kb = SEARCH_INDEX.stat().st_size / 1024
    print(f"  search_index.json　({n_idx} 筆，{kb:,.0f} KB，首頁搜尋用)")

    total = sum(len(i["body"]) for i in data)
    print(f"\n完成：{len(written)} 頁，內容共 {total:,} 字")
    print(f"預覽： {ROOT / 'articles' / 'index.html'}")

    if args.serve:
        import http.server
        import socketserver
        import webbrowser
        import os
        os.chdir(ROOT)
        with socketserver.TCPServer(("", 8902), http.server.SimpleHTTPRequestHandler) as httpd:
            print("預覽伺服器 http://localhost:8902/articles/ （Ctrl+C 結束）")
            webbrowser.open("http://localhost:8902/articles/")
            httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
