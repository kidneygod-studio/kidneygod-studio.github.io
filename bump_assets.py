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
PAGES = ("index.html", "game.html", "library.html", "dash.html")


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


def bump_sw(ver):
    """把整站內容摘要寫進 sw.js 的 VERSION。

    Service Worker 的快取名字要跟著內容一起變，否則改版之後使用者會停在
    舊快取上。這裡把三個頁面加上四支 js 的雜湊再壓成一個短碼 —— 任何一處
    有改動，快取名就換，activate 時舊的會整批清掉。
    """
    if not os.path.exists("sw.js"):
        return
    h = hashlib.md5()
    for f in list(ASSETS) + list(PAGES):
        if os.path.exists(f):
            h.update(io.open(f, "rb").read())
    tag = "kg-" + h.hexdigest()[:10]
    s = old = io.open("sw.js", encoding="utf-8").read()
    s = re.sub(r'const VERSION = "[^"]*";', f'const VERSION = "{tag}";', s)
    if s != old:
        io.open("sw.js", "w", encoding="utf-8").write(s)
        print(f"  sw.js        VERSION={tag}")
    else:
        print(f"  sw.js        VERSION={tag}（未變動）")


if __name__ == "__main__":
    main()
