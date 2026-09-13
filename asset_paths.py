# -*- coding: utf-8 -*-
"""原始素材的位置解析。所有產生器共用這一支。

素材（logo 原圖、知識卡插圖、貓咪貼圖）**不進版控**：太大，而且進了 git
歷史就永遠拿不掉。repo 裡只留壓過的產出，素材本身放在雲端同步資料夾，
兩台機器共用。

為什麼要有這一支：原本五支產生器各自把路徑寫死成
`C:\\Users\\user\\Downloads\\...`。搬到 macOS 之後那些路徑全部失效，
而且是**五個地方各壞各的**。更糟的是 check_site.py 會因此回傳 1，
publish_daily.py 看到非 0 就拒絕發佈——每日新知從搬機之後就一次都沒上線過。
路徑集中到這裡之後，換機器只要確認一個地方。

解析順序：
  1. 環境變數 `KIDNEYGOD_ASSETS`——任何機器、任何平台都能用它覆寫
  2. Google Drive 的預設位置（macOS 與 Windows 的常見路徑都試）
  3. repo 內的 `assets_src/`——單機備援，.gitignore 擋著

**找不到不是錯誤。** 素材只有在「重新產生」時才需要（重做 logo、重新匯入
插圖）。網站本身跑不到它們——線上要的是 `og/`、`cards/`、`gi/` 這些已經
壓好、已經進版控的產出。所以這裡回傳的路徑可能不存在，呼叫端要自己判斷，
而 check_site.py 對這一項只警告、不擋發佈。
"""
from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent

# 資料夾名稱。雲端與本機備援都用同一個名字，換機器時比較不會找錯。
ASSETS_DIRNAME = "kidneygod_assets"

# 素材檔名／子資料夾名。集中在這裡，改名時只改一處。
LOGO_PNG = "kidneygod.png"          # 1678×937 白底 .NET 版
GI_ART = "知識卡插圖"                # 知識卡插圖（第一批）
GI_ART2 = ("知識卡插圖", "知識卡插圖2")   # 第二批，原本就是巢狀在第一批底下
STICKERS = "貓咪貼圖"
HERO_SRC = "hero_src"               # 長文大圖的原圖


def hero_src_dir() -> pathlib.Path:
    """長文大圖原圖的所在。

    先看 repo 內的 hero_src——它可能是實體資料夾，也可能是指向雲端的
    符號連結（早期的作法）。都沒有才用雲端素材根目錄底下的 hero_src。

    這個順序讓兩種作法並存：已經建好符號連結的機器照舊，新機器什麼都
    不用設定，直接把圖丟進雲端資料夾就會被找到。
    """
    local = ROOT / HERO_SRC
    if local.exists():
        return local
    return assets_root() / HERO_SRC


def _candidates() -> list[pathlib.Path]:
    """可能的素材根目錄，依優先序。"""
    out: list[pathlib.Path] = []

    env = os.environ.get("KIDNEYGOD_ASSETS")
    if env:
        out.append(pathlib.Path(env).expanduser())

    home = pathlib.Path.home()

    # macOS 的 Google Drive for Desktop。~/Google Drive 是指向
    # ~/Library/CloudStorage/GoogleDrive-<帳號>/ 的符號連結，兩條都試——
    # 有些機器只有其中一條。帳號 email 不寫死，用 glob。
    for drive in [home / "Google Drive",
                  *sorted((home / "Library" / "CloudStorage").glob("GoogleDrive-*"))]:
        for mydrive in ("我的雲端硬碟", "My Drive"):
            out.append(drive / mydrive / ASSETS_DIRNAME)

    # Windows：Google Drive 常掛成 G:\，也可能在使用者目錄底下
    for drive in (pathlib.Path("G:/"), pathlib.Path("H:/"), home / "Google Drive"):
        for mydrive in ("我的雲端硬碟", "My Drive"):
            out.append(drive / mydrive / ASSETS_DIRNAME)

    # 單機備援：repo 內的 assets_src/（.gitignore 擋著）
    out.append(ROOT / "assets_src")

    # 去重但保留順序
    seen, uniq = set(), []
    for p in out:
        if str(p) not in seen:
            seen.add(str(p))
            uniq.append(p)
    return uniq


def assets_root() -> pathlib.Path:
    """素材根目錄。找不到任何存在的候選時，回傳第一個候選當作「應該放這裡」，
    好讓錯誤訊息能告訴使用者該把檔案放到哪。"""
    cands = _candidates()
    for p in cands:
        if p.is_dir():
            return p
    return cands[0]


def asset(*parts: str) -> pathlib.Path:
    """素材路徑。回傳的路徑不保證存在——呼叫端要自己檢查。"""
    return assets_root().joinpath(*parts)


def probe(p, timeout=5.0):
    """素材存在狀態：回傳 "ok" / "missing" / "empty" / "timeout" / "error:…"。

    ⚠ **整段探查一定要有逾時。** 素材放在 Google Drive 的掛載點上，而雲端
    檔案系統可能在 open()／scandir() 上無限期阻塞——不是回錯誤，是不回。

    2026-09-14 就是這樣：check_site 這一項用 rglob 遞迴走訪 Drive 資料夾，
    卡在核心的 open() 十幾分鐘，publish_daily.py 整條管線跟著停住。那比它
    原本要修的問題更糟：原本是「檢查失敗、擋下發佈」，變成「檢查不會結束」。
    sample 堆疊底部是 builtin_any → gen_iternext → os_scandir → open$NOCANCEL。

    所以把探查丟到 daemon 執行緒，逾時就當作「不知道」。素材這一項在
    check_site.py 裡本來就是 WARN_ONLY——**寧可少報一次，不可卡住整條管線**。

    放在這裡而不是 check_site.py：凡是要碰雲端素材路徑的都該走這一支。
    同樣的逾時保護抄成兩份，總有一份會在改動時被漏掉，然後又卡住。
    """
    import threading

    box = {}

    def work():
        try:
            if not p.exists():
                box["r"] = "missing"
            elif not p.is_dir():
                box["r"] = "ok"
            else:
                # 遞迴數「檔案」，但看到第一個就停（any 會短路）：知識卡插圖
                # 底下巢狀著 知識卡插圖2，只有空殼時 iterdir() 仍然非空，
                # 一張圖都沒有卻會報成通過。
                box["r"] = "ok" if any(f.is_file() for f in p.rglob("*")) else "empty"
        except OSError as e:
            box["r"] = f"error:{e.strerror}"

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    return box.get("r", "timeout")


def describe() -> str:
    """給錯誤訊息用的一句話。"""
    root = assets_root()
    state = "存在" if root.is_dir() else "不存在"
    return (f"素材根目錄：{root}（{state}）\n"
            f"  可用環境變數 KIDNEYGOD_ASSETS 指到別的地方。\n"
            f"  素材不進版控，需要時從雲端同步資料夾取得。")


if __name__ == "__main__":
    print(describe())
    print()
    for label, p in (("logo 原圖", asset(LOGO_PNG)),
                     ("知識卡插圖", asset(GI_ART)),
                     ("知識卡插圖2", asset(*GI_ART2)),
                     ("貓咪貼圖", asset(STICKERS))):
        # 走 probe()：它有逾時保護。這支的用途之一就是讓人在拿回素材後
        # 自己驗收（PICKUP_FROM_HOSPITAL.md 叫使用者跑這一行），所以絕不能
        # 因為雲端沒回應就整個卡住。
        mark, note = {
            "ok":      ("✓", ""),
            "missing": ("✗", "（不存在）"),
            "empty":   ("✗", "（空的）"),
            "timeout": ("?", "（雲端沒回應，逾時）"),
        }.get(r := probe(p), ("?", f"（{r}）"))
        print(f"  {mark} {label:<12} {p} {note}")
