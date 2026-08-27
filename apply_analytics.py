"""一鍵套用（或移除）Cloudflare Web Analytics。

網站有兩種頁面：build_site.py 產生的靜態頁，以及手寫的商城三頁。
token 要同時進到這兩邊，手改容易漏，所以集中在這裡。

用法：
    python apply_analytics.py --token 你的beacon token
    python apply_analytics.py --remove          # 拿掉追蹤
    python apply_analytics.py --status          # 只看目前狀態

取得 token：Cloudflare 免費帳號 → Web Analytics → Add a site
→ 網域填 kidneygod.net → 複製 data-cf-beacon 裡的 token 字串。
不需要把 DNS 搬到 Cloudflare，JS beacon 在任何主機上都能用。
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build_site.py"
HANDWRITTEN = ["shop.html", "game.html", "library.html"]

# dash.html（站長儀表板）刻意不追蹤：沒有對外連結、不在 sitemap，
# 只有你自己會開。加進去只會讓自己的後台瀏覽污染統計數字。
EXCLUDED = ["dash.html"]

# 比對時放寬 script 標籤的屬性寫法，這樣即使之前用 defer 版本注入過也認得出來，
# 重跑不會留下兩份。
BEACON_RE = re.compile(
    r'\n?[ \t]*(?:<!-- Cloudflare Web Analytics -->)?'
    r'<script [^>]*src=[\'"]https://static\.cloudflareinsights\.com/beacon\.min\.js[\'"][^>]*>'
    r'</script>(?:<!-- End Cloudflare Web Analytics -->)?')


def beacon(token: str) -> str:
    # 寫法對齊 Cloudflare 目前發的片段（type="module"，本身就是延後執行）
    return ('\n<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" '
            f'data-cf-beacon=\'{{"token": "{token}"}}\'></script>')


def read(p: Path) -> str:
    return io.open(p, encoding="utf-8").read()


def write(p: Path, s: str) -> None:
    io.open(p, "w", encoding="utf-8", newline="").write(s)


def current_token() -> str:
    m = re.search(r'^ANALYTICS_TOKEN = "(.*)"', read(BUILD), re.M)
    return m.group(1) if m else ""


def set_build_token(token: str) -> None:
    s = read(BUILD)
    s2, n = re.subn(r'^ANALYTICS_TOKEN = ".*"', f'ANALYTICS_TOKEN = "{token}"', s, count=1, flags=re.M)
    if not n:
        sys.exit("在 build_site.py 找不到 ANALYTICS_TOKEN，請確認檔案沒有被改過")
    write(BUILD, s2)


def set_handwritten(token: str) -> list[str]:
    """手寫頁直接注入 </body> 前。重複執行會先移除舊的再放新的，不會疊加。"""
    touched = []
    for name in HANDWRITTEN:
        p = ROOT / name
        s = old = read(p)
        s = BEACON_RE.sub("", s)
        # 移除留下的空白若不收乾淨，每跑一次就會多一個空行
        s = re.sub(r"\s*\n</body>", "\n</body>", s, count=1)
        if token:
            s = s.replace("</body>", beacon(token).lstrip("\n") + "\n</body>", 1)
        if s != old:
            write(p, s)
            touched.append(name)
    return touched


def status() -> None:
    tok = current_token()
    print(f"build_site.py　ANALYTICS_TOKEN = {tok or '（未設定）'}")
    for name in HANDWRITTEN:
        has = bool(BEACON_RE.search(read(ROOT / name)))
        print(f"{name:<16}{'已注入 beacon' if has else '無'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", help="Cloudflare Web Analytics 的 beacon token")
    ap.add_argument("--remove", action="store_true", help="移除所有追蹤程式碼")
    ap.add_argument("--status", action="store_true", help="只顯示目前狀態")
    ap.add_argument("--no-build", action="store_true", help="不要接著重建靜態頁")
    a = ap.parse_args()

    if a.status or not (a.token or a.remove):
        status()
        return 0

    token = "" if a.remove else a.token.strip()
    if token and not re.fullmatch(r"[0-9a-f]{32}", token):
        # Cloudflare 的 token 是 32 位十六進位字串。貼錯（例如整段 script）在這裡就擋下來，
        # 不要等到部署後才發現統計沒進來。
        print(f"警告：token 看起來不像 Cloudflare beacon token（預期 32 位十六進位）\n"
              f"      收到的是：{token[:60]}{'…' if len(token) > 60 else ''}")
        if input("仍要繼續嗎？(y/N) ").strip().lower() != "y":
            return 1

    set_build_token(token)
    touched = set_handwritten(token)
    print(f"build_site.py　{'已清除 token' if a.remove else '已寫入 token'}")
    print(f"手寫頁　　　　{('、'.join(touched)) if touched else '無變更'}")

    if not a.no_build:
        print("\n重建靜態頁：")
        subprocess.run([sys.executable, str(ROOT / "build_site.py")], check=True)

    print("\n目前狀態：")
    status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
