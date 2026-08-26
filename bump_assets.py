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


if __name__ == "__main__":
    main()
