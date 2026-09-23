# -*- coding: utf-8 -*-
r"""長文上線後，寄一封審閱請求信給作者。

    python request_review.py high-potassium-ckd
    python request_review.py articles/high-potassium-ckd.html

信裡有兩個連結：
    1. 文章本身（已經上線，直接讀）
    2. /admin.html?p=<路徑> —— 看完按一下就記錄審閱日期

為什麼是「先上線、後補審閱日期」（2026-09-23 作者定案）：
內容早點被 Google 索引比較重要，而「醫師審閱」這個聲明晚一點出現是誠實的。
沒有審閱紀錄時，build_site.py 本來就不會印那行字，也不會輸出 lastReviewed。

為什麼不用「已讀即視為同意」：
追蹤像素回答的是「有沒有東西抓了這張圖」，不是「醫師看過了沒有」。
iPhone 的郵件隱私權保護會預先載入所有遠端內容，Gmail 會經過代理快取，
所以信一送到就可能回報已開啟。用那個來支撐公開醫療網站上的「醫師已審閱
＋日期」，等於把 reviewed.json 當初存在的理由抵銷掉。
admin.html 的寫入限定 Google 登入且信箱相符，那是真正的身分驗證。
（另外，目前的 Resend API key 是「只能寄信」的受限金鑰，本來也讀不到事件。）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SITE = "https://kidneygod.net"
# email_delivery 住在另一個專案，那裡才有 Resend 設定與重試邏輯，不要另外再寫一份
sys.path.insert(0, r"C:\Users\user\nephrology_digest\scripts")


def resolve(arg: str) -> str:
    """slug 或相對路徑 → 網站相對路徑（articles/<slug>.html）。"""
    p = arg.strip().lstrip("/")
    if not p.endswith(".html"):
        p = f"articles/{p}.html"
    if not (ROOT / p).exists():
        sys.exit(f"找不到 {p}——先建站再寄信，不然信裡的連結會是 404。")
    return p


def title_of(path: str) -> str:
    html = (ROOT / path).read_text(encoding="utf-8", errors="replace")
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    t = re.sub(r"\s+", " ", m.group(1)).strip() if m else path
    # 站名後綴對信件標題沒有意義
    return re.sub(r"\s*[|｜–—-]\s*護腎教室.*$", "", t).strip() or path


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("用法：python request_review.py <slug 或 articles/xxx.html>")
    path = resolve(sys.argv[1])
    title = title_of(path)
    url = f"{SITE}/{path}"
    admin = f"{SITE}/admin.html?p={path}"

    html = f"""<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
 max-width:560px;margin:0 auto;padding:8px 4px;color:#1a2330;line-height:1.75">
<p style="font-size:13px;color:#6b7785;margin:0 0 6px">護腎教室・長文審閱</p>
<h2 style="font-size:19px;margin:0 0 14px;line-height:1.5">{title}</h2>
<p style="margin:0 0 18px">這篇已經上線，但<b>還沒有標示醫師審閱</b>。
你看完覺得沒問題的話，按下面那個按鈕，網站上就會出現
「本頁內容最後由吳政哲醫師審閱於（今天日期）」。</p>
<p style="margin:0 0 10px"><a href="{url}"
 style="color:#1f6f8b;font-weight:700">先讀文章 →</a></p>
<p style="margin:22px 0"><a href="{admin}"
 style="display:inline-block;background:#1f6f8b;color:#fff;text-decoration:none;
 padding:13px 22px;border-radius:9px;font-weight:700">我已看過，可標示醫師審閱</a></p>
<p style="font-size:13px;color:#6b7785;margin:0 0 6px">
按鈕會開後台，需要用你的 Google 帳號登入（認的是身分，不是網址保密）。
按下去只記到雲端，隔天早上的排程會把日期同步進網站。</p>
<p style="font-size:13px;color:#6b7785;margin:0">
<b>要改內容就直接回我，不要按。</b>沒有按就不會出現審閱日期——
不按等於維持現狀，不會有東西自己上線。</p>
</div>"""

    text = (f"護腎教室・長文審閱\n\n{title}\n\n"
            f"這篇已上線，但還沒標示醫師審閱。\n\n"
            f"讀文章：{url}\n"
            f"確認審閱：{admin}\n\n"
            f"要改內容就直接回信，不要按。沒按就不會出現審閱日期。")

    if "--dry-run" in sys.argv:
        print("--dry-run：沒有寄出。這封信會長這樣：\n")
        print(f"  標題：[護腎教室] 請確認審閱：{title}")
        print(f"  文章：{url}")
        print(f"  確認：{admin}")
        print(f"  內文（純文字版）：\n{text}")
        return

    import email_delivery as e
    res = e.send_mail(f"[護腎教室] 請確認審閱：{title}", html, text)
    print(f"已寄出審閱請求（Resend id: {res.get('id')}）")
    print(f"  文章：{url}")
    print(f"  確認：{admin}")


if __name__ == "__main__":
    main()
