# -*- coding: utf-8 -*-
"""把 shared.js / sync.js / quiz.js 的內容雜湊寫進 script 標籤的 ?v=。

GitHub Pages 對 html 與 js 都送 Cache-Control: max-age=600，改完 js 推上去，
使用者的瀏覽器還會用舊檔十分鐘。網址帶著內容雜湊就不會有這個空窗：
內容一改，網址就變，瀏覽器一定重抓；內容沒改則沿用快取。

每次改動這三支 js 之後執行一次：
    python bump_assets.py
"""
import io, os, re, sys, hashlib

sys.stdout.reconfigure(encoding="utf-8")

ASSETS = ("shared.js", "data.js", "sync.js", "quiz.js")

# 會載入上述 js、需要改寫 ?v= 的頁面。
# 註：首頁 index.html 已改為衛教文章頁（由 build_site.py 產生、不載入這些 js），
#     原本的商城搬到 shop.html，所以要改的是 shop.html 而不是 index.html。
PAGES = ("shop.html", "game.html", "library.html", "dash.html")

# 不需要改寫 ?v=，但內容變動時仍應讓 Service Worker 換快取版本的檔案
#
# 圖片必須列入：sw.js 對圖片採「快取優先」，而圖片網址沒有 ?v= 可以帶版本。
# 換了圖卻沒換 VERSION 的話，造訪過的人會從快取拿到舊圖，而且永遠不會更新
# ——沒有任何錯誤訊息，只是圖一直是舊的。2026-08-28 換醫師照時實際踩到。
#
# food_db.json 同理：它是 .json，在 sw.js 裡也走快取優先，而且網址沒有 ?v=。
# 更新營養資料卻不換 VERSION 的話，造訪過的人會一直拿到舊的成分數值。
HASH_ONLY = ("index.html", "logo.png", "doctor.jpg", "apple-touch-icon.png",
             "food_db.json")

# 整個目錄都要計入雜湊的。知識卡圖片是 sw.js 快取優先、網址又不帶 ?v=，
# 換了圖卻沒換 VERSION 的話，看過那張卡的人會永遠停在舊圖上而且毫無錯誤訊息。
# 2026-08-31 換上 40 張新插圖時發現這裡漏了 cards/gi。
HASH_DIRS = ("cards/gi",)


def main():
    ver = {f: hashlib.md5(io.open(f, "rb").read()).hexdigest()[:8] for f in ASSETS}
    changed = []
    for page in PAGES:
        if not os.path.exists(page):
            continue
        s = old = io.open(page, encoding="utf-8").read()
        for f, v in ver.items():
            s = re.sub(r'src="' + re.escape(f) + r'(\?v=[0-9a-f]+)?"',
                       f'src="{f}?v={v}"', s)
        if s != old:
            io.open(page, "w", encoding="utf-8").write(s)
            changed.append(page)
    for f, v in ver.items():
        print(f"  {f:12} v={v}")
    print(f"更新了 {len(changed)} 個頁面 {changed or '（版本號已是最新）'}")
    bump_sw(ver)


def sw_version():
    """算出目前內容對應的 VERSION，不寫檔。

    抽成獨立函式是為了讓 check_site.py 能重用同一份邏輯——各自實作一份
    遲早會走鐘，而走鐘的後果正是這個版本號要防的那種靜默錯誤。
    回傳 None 表示沒有 sw.js。
    """
    if not os.path.exists("sw.js"):
        return None
    h = hashlib.md5()
    for f in list(ASSETS) + list(PAGES) + list(HASH_ONLY):
        if os.path.exists(f):
            h.update(io.open(f, "rb").read())
    # 目錄要排序後再逐檔計入，否則檔案系統的列舉順序一變，內容沒動版本號也會變
    for d in HASH_DIRS:
        for root, _dirs, files in sorted(os.walk(d)):
            for f in sorted(files):
                p = os.path.join(root, f)
                h.update(p.replace("\\", "/").encode("utf-8"))
                h.update(io.open(p, "rb").read())
    # sw.js 自己的內容也要計入，否則改了快取策略卻不換版本號，
    # 舊快取不會被清掉。把 VERSION 那行剔除以免自我循環。
    sw_body = re.sub(r'const VERSION = "[^"]*";', "", io.open("sw.js", encoding="utf-8").read())
    h.update(sw_body.encode("utf-8"))
    return "kg-" + h.hexdigest()[:10]


def bump_sw(ver):
    """把整站內容摘要寫進 sw.js 的 VERSION。

    Service Worker 的快取名字要跟著內容一起變，否則改版之後使用者會停在
    舊快取上；activate 時舊的會整批清掉。
    """
    tag = sw_version()
    if tag is None:
        return
    s = old = io.open("sw.js", encoding="utf-8").read()
    s = re.sub(r'const VERSION = "[^"]*";', f'const VERSION = "{tag}";', s)
    if s != old:
        io.open("sw.js", "w", encoding="utf-8").write(s)
        print(f"  sw.js        VERSION={tag}")
    else:
        print(f"  sw.js        VERSION={tag}（未變動）")


if __name__ == "__main__":
    main()
