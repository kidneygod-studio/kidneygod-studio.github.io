# -*- coding: utf-8 -*-
"""建置後的對帳檢查：抓「不會噴錯、但使用者看到的是錯的」那一類問題。

這支腳本的每一項都對應一次真實事故，不是憑空想像的規則：

  2026-08-28  換醫師照片，圖片沒列進快取雜湊 → 造訪過的人永遠看到舊照
  2026-08-31  換 40 張知識卡插圖，cards/gi 沒列進雜湊 → 同上
  2026-08-31  shop/library 漏了 text-size-adjust → 手機字級被瀏覽器改掉
  2026-08-31  make_logo.py 的來源沒跟上換網域 → 跑一次就把網域換回舊的
  （持續）    data.js 與 knowledge_export.json 是兩份不同步的複本

共同點都是「產生器與它產生的資產各自演進，沒有人對帳」。這類錯誤沒有
例外訊息、沒有破圖，只有使用者看到舊的或錯的東西，所以只能主動去查。

用法：
    python check_site.py          全部檢查，有問題回傳 1
    python check_site.py -v       連通過的細節也印出來
"""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent
VERBOSE = "-v" in sys.argv

# 掃描 HTML 時要跳過的：卡片圖產出目錄沒有 HTML，備份與相依套件也不是我們的
SKIP_DIRS = {".git", "node_modules", "__pycache__", "cards"}
# dash.html 是站長自己的儀表板（帶 noindex），專案本來就把它排除在分析、
# 預覽圖與 sitemap 之外，這裡沿用同一條界線
SKIP_FILES = {"dash.html"}


def html_files():
    for p in sorted(ROOT.rglob("*.html")):
        if any(part in SKIP_DIRS for part in p.relative_to(ROOT).parts):
            continue
        if p.name in SKIP_FILES:
            continue
        yield p


def rel(p) -> str:
    return str(pathlib.Path(p).relative_to(ROOT)).replace("\\", "/")


# ── 1. 兩份卡片資料是否同步 ──────────────────────────────────────────
# data.js（商城與收藏冊用）與 knowledge_export.json（衛教網站用）存的是
# 同一批知識，但沒有任何機制讓它們同步。改一邊忘了另一邊不會有錯誤訊息，
# 只是兩處顯示的內容從此不一樣。
NODE_DUMP = r"""
const fs = require('fs');
// argv[0]=node、argv[1]=這支 helper，要的檔案在 argv[2]
const src = fs.readFileSync(process.argv[2], 'utf8');
// 用 new Function 而不是 eval：const 宣告在函式主體內是取得到的
const fn = new Function(src + '\nreturn typeof PRODUCTS !== "undefined" ? PRODUCTS : null;');
process.stdout.write(JSON.stringify(fn()));
"""


def load_products():
    """用 node 實際執行 data.js 取得 PRODUCTS。

    data.js 是 JS 不是 JSON（鍵沒有引號、內文含中文引號與跳脫），用正則
    硬拆遲早會拆錯，而拆錯的檢查比沒有檢查更糟。
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(NODE_DUMP)
        helper = f.name
    try:
        out = subprocess.run(["node", helper, str(ROOT / "data.js")],
                             capture_output=True, text=True, encoding="utf-8",
                             timeout=60)
        if out.returncode != 0:
            return None, f"node 解析 data.js 失敗：{out.stderr.strip()[:200]}"
        return json.loads(out.stdout), None
    except FileNotFoundError:
        return None, "找不到 node，無法安全解析 data.js（跳過這項）"
    except Exception as e:
        return None, f"解析 data.js 失敗：{type(e).__name__} {e}"
    finally:
        os.unlink(helper)


def check_card_data_sync():
    products, err = load_products()
    if products is None:
        return [err] if err and "跳過" not in err else []

    cards = json.loads((ROOT / "knowledge_export.json").read_text("utf-8"))
    js = {p["id"]: p for p in products}
    ex = {c["id"]: c for c in cards}

    bad = []
    only_js, only_ex = set(js) - set(ex), set(ex) - set(js)
    if only_js:
        bad.append(f"只在 data.js 有：{sorted(only_js)[:5]}")
    if only_ex:
        bad.append(f"只在 knowledge_export.json 有：{sorted(only_ex)[:5]}")

    for cid in sorted(set(js) & set(ex)):
        k = js[cid].get("k") or {}
        if (k.get("t") or "").strip() != (ex[cid].get("title") or "").strip():
            bad.append(f"{cid} 標題不一致")
        if (k.get("b") or "").strip() != (ex[cid].get("body") or "").strip():
            bad.append(f"{cid} 內文不一致")
    if VERBOSE and not bad:
        print(f"    兩份各 {len(js)} 筆，id、標題、內文皆一致")
    return bad


# ── 2. 每張卡的插圖與產出是否齊全 ────────────────────────────────────
def check_card_assets():
    cards = json.loads((ROOT / "knowledge_export.json").read_text("utf-8"))
    art_dir, out_dir = ROOT / "gi" / "art", ROOT / "cards" / "gi"
    have_art = {p.stem for p in art_dir.glob("*") if p.is_file()}
    bad = []
    for c in cards:
        cid = c["id"]
        if cid not in have_art:
            bad.append(f"{cid} 沒有插圖來源 gi/art/{cid}.*（會退回程式繪製的後備圖）")
        for sub in ("", "thumb"):
            if not (out_dir / sub / f"{cid}.png").exists():
                bad.append(f"{cid} 缺產出 cards/gi/{sub + '/' if sub else ''}{cid}.png")
    orphan = have_art - {c["id"] for c in cards}
    if orphan:
        bad.append(f"gi/art 有多餘檔案（對不到任何卡片）：{sorted(orphan)[:5]}")
    if VERBOSE and not bad:
        print(f"    {len(cards)} 張卡的插圖來源與產出（含縮圖）都在")
    return bad


# ── 3. HTML 引用的本地檔案是否存在 ───────────────────────────────────
# content= 只查圖片類的 meta，不然會把 og:title 之類的純文字也當成路徑
REF_RE = re.compile(
    r'(?:\b(?:src|href)="([^"]+)")'
    r'|(?:property="(?:og|twitter):image"\s+content="([^"]+)")'
    r'|(?:name="twitter:image"\s+content="([^"]+)")')


def check_local_refs():
    bad = []
    checked = 0
    for p in html_files():
        h = p.read_text("utf-8", "replace")
        for m in REF_RE.finditer(h):
            u = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            # 外部連結、行內資料、錨點、範本字串一律不查
            if (not u or u.startswith(("http://", "https://", "//", "data:",
                                       "mailto:", "tel:", "#"))
                    or "${" in u or u.startswith("{{")):
                continue
            path = u.split("?")[0].split("#")[0]
            if not path or not re.search(r"\.[a-z0-9]{2,5}$", path, re.I):
                continue          # 目錄連結（/articles/）交給伺服器處理
            target = (ROOT / path.lstrip("/")) if path.startswith("/") \
                else (p.parent / path)
            checked += 1
            if not target.exists():
                bad.append(f"{rel(p)} → {u}")
    if VERBOSE and not bad:
        print(f"    檢查 {checked} 個本地引用，全部存在")
    return bad


# ── 4. 用了沒定義的 CSS 變數 ─────────────────────────────────────────
# 衛教站用 --fg/--bg/--card/--mut，商城自成一套用 --ink。把商城的變數名
# 寫進衛教站不會報錯，只是靜默失效——淺色模式下退回繼承值看起來正常，
# 深色模式才爆掉。這一項就是為了擋這種混用。
def check_css_vars():
    bad = []
    for p in html_files():
        h = p.read_text("utf-8", "replace")
        css = "\n".join(re.findall(r"(?s)<style[^>]*>(.*?)</style>", h))
        if not css:
            continue
        defined = set(re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", css))
        # 只查沒有預設值的 var(--x)。寫成 var(--fs,1) 是刻意的——預設值就是
        # 平常生效的值，變數由 JS 在執行期才設定，不算漏定義。
        # 行內 style 也會用到變數，所以整份 HTML 都要掃。
        used = set(re.findall(r"var\(\s*(--[a-zA-Z0-9_-]+)\s*\)", h))
        missing = used - defined
        if missing:
            bad.append(f"{rel(p)} 用了未定義的變數：{sorted(missing)}")
    if VERBOSE and not bad:
        print("    每個頁面用到的 CSS 變數都有定義")
    return bad


# ── 5. 手機字級是否被瀏覽器接管 ──────────────────────────────────────
# Android Chrome 會自動放大「一整段文字」，橫放時區塊變寬更容易觸發。
# 少了這一行，CSS 寫的字級形同虛設。
def check_text_size_adjust():
    bad = []
    for p in html_files():
        h = p.read_text("utf-8", "replace")
        if "<body" not in h:
            continue
        if "text-size-adjust" not in h:
            bad.append(f"{rel(p)} 缺 text-size-adjust（手機字級會被瀏覽器改掉）")
    if VERBOSE and not bad:
        print("    所有頁面都關掉了瀏覽器的自動字體放大")
    return bad


# ── 6. sw.js 的快取版本號是不是最新的 ────────────────────────────────
# 圖片是快取優先且網址不帶 ?v=，版本號沒跟著換的話，看過那張圖的人會
# 永遠停在舊圖，而且沒有任何錯誤訊息。
def check_sw_version():
    sys.path.insert(0, str(ROOT))
    cwd = os.getcwd()
    try:
        os.chdir(ROOT)
        import bump_assets
        want = bump_assets.sw_version()
    except Exception as e:
        return [f"無法計算應有的版本號：{type(e).__name__} {e}"]
    finally:
        os.chdir(cwd)
    if want is None:
        return []
    have = re.search(r'const VERSION = "([^"]+)"',
                     (ROOT / "sw.js").read_text("utf-8"))
    have = have.group(1) if have else "(找不到)"
    if have != want:
        return [f"sw.js 是 {have}，內容對應的應該是 {want}"
                f"——請跑 python bump_assets.py"]
    if VERBOSE:
        print(f"    VERSION={have}，與目前內容相符")
    return []


# ── 7. 產生器的來源檔還在不在 ────────────────────────────────────────
# 來源放在 repo 外（Downloads），搬機或整理檔案時會消失；等到要重跑
# 產生器才發現就太晚了。
SRC_PATTERNS = {
    "make_logo.py": r'^SRC = r?"([^"]+)"',
    "make_og.py": r'^LOGO = pathlib\.Path\(r?"([^"]+)"\)',
    "import_gi_art2.py": r'^SRC = r?"([^"]+)"',
}


def check_generator_sources():
    bad = []
    for fname, pat in SRC_PATTERNS.items():
        f = ROOT / fname
        if not f.exists():
            continue
        m = re.search(pat, f.read_text("utf-8", "replace"), re.M)
        if not m:
            bad.append(f"{fname} 找不到來源設定（檢查規則可能過期了）")
            continue
        if not pathlib.Path(m.group(1)).exists():
            bad.append(f"{fname} 的來源不存在：{m.group(1)}")
        elif VERBOSE:
            print(f"    {fname} → {m.group(1)}")
    return bad


CHECKS = [
    ("卡片資料兩份是否同步", check_card_data_sync),
    ("卡片插圖與產出是否齊全", check_card_assets),
    ("HTML 引用的本地檔案", check_local_refs),
    ("CSS 變數有無用了沒定義的", check_css_vars),
    ("手機字級是否被接管", check_text_size_adjust),
    ("快取版本號是否最新", check_sw_version),
    ("產生器的來源檔", check_generator_sources),
]


def main() -> int:
    fails = 0
    for name, fn in CHECKS:
        try:
            problems = fn()
        except Exception as e:
            problems = [f"檢查本身出錯：{type(e).__name__} {e}"]
        if problems:
            fails += 1
            print(f"✗ {name}（{len(problems)} 項）")
            for x in problems[:12]:
                print(f"    {x}")
            if len(problems) > 12:
                print(f"    …另外還有 {len(problems) - 12} 項")
        else:
            print(f"✓ {name}")
            if VERBOSE:
                fn()      # 讓通過的細節也印出來
    print()
    if fails:
        print(f"有 {fails} 項沒過。上面每一項都是「不會噴錯但使用者看到錯的」那一類。")
    else:
        print("全部通過。")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
