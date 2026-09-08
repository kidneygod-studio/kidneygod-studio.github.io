#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把指定日期的每日文獻摘要匯入網站並推上線，一支跑完。

給 Telegram 的 Dr. Shock BOT 用：作者在對話裡說「2026/9/7 可上線」，
bot 就呼叫這支。也可以手動跑：

    python publish_digest.py 2026-09-07
    python publish_digest.py 2026-09-07 2026-09-08
    python publish_digest.py --dry-run 2026-09-07     只看會匯入什麼

做的事就是原本手動那一串：

    import_digests.py --write --only <日期>
    build_site.py → bump_assets.py → check_site.py
    git add（只加這條流程會動到的路徑）→ commit → push

**設計上刻意不做的事**

1. 工作區有沒 commit 的改動就中止。這支會 commit，若順手把作者
   正在改到一半的東西一起送上線，事後很難拆。
2. 落後遠端就中止。這台是唯一的發佈來源，落後代表有別的地方推過，
   盲目 push 會失敗或蓋掉東西。
3. `git add -A` 不用，改成逐一列出路徑。理由同 1。
4. check_site.py 沒過就不 commit。網站壞掉比晚一天上線嚴重。

任何一步失敗都直接結束並把原因印出來（bot 會把這段原文轉給作者）。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
PY = sys.executable

# build_site.py 會動到的東西。列成清單而不是 -A，見檔頭說明。
PATHS = [
    "articles_src/news.json",
    "articles",
    "index.html",
    "sw.js",
    "sitemap.xml",
    "robots.txt",
    "search_index.json",
]


class Stop(Exception):
    """帶著要回報給作者的訊息中止。"""


def run(args: list[str], cwd: Path = ROOT) -> str:
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise Stop(f"`{' '.join(args[1:] if args[0] == PY else args)}` 失敗\n"
                   + (p.stdout or "")[-800:] + (p.stderr or "")[-800:])
    return p.stdout or ""


def git(*args: str) -> str:
    return run(["git", *args])


def preflight() -> None:
    dirty = git("status", "--porcelain").strip()
    if dirty:
        raise Stop("工作區還有沒 commit 的改動，先處理完再上線：\n"
                   + "\n".join(dirty.splitlines()[:12]))
    git("fetch", "--quiet", "origin")
    behind = git("rev-list", "--count", "HEAD..@{u}").strip()
    if behind not in ("", "0"):
        raise Stop(f"本地落後遠端 {behind} 個 commit，先 git pull 再上線")


def n_importable(dates: list[str]) -> tuple[int, str]:
    """跑一次預覽，回傳（可匯入篇數, 完整報表）。"""
    args = [PY, "import_digests.py"]
    for d in dates:
        args += ["--only", d]
    out = run(args)
    m = re.search(r"可匯入 (\d+) 篇", out)
    return (int(m.group(1)) if m else 0), out


def titles_added() -> list[str]:
    """從 news.json 的 diff 撈出新增的標題，用來寫 commit 訊息與回報。"""
    diff = git("diff", "--cached", "--", "articles_src/news.json")
    return re.findall(r'^\+\s*"zh":\s*"(.+?)",?$', diff, re.M)


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    dates = []
    for a in argv:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a):
            raise Stop(f"日期要寫成 YYYY-MM-DD，收到：{a}")
        dates.append(a)
    if not dates:
        raise Stop("要指定日期，例如：python publish_digest.py 2026-09-07")

    n, report = n_importable(dates)
    if dry:
        print(report)
        return 0
    if n == 0:
        raise Stop(f"{'、'.join(dates)} 這幾天沒有可匯入的新論文"
                   "（可能已經上線過，或三篇都被期刊規則擋掉）。\n\n"
                   + report[report.find("可匯入"):][:900])

    preflight()

    args = [PY, "import_digests.py", "--write"]
    for d in dates:
        args += ["--only", d]
    run(args)
    run([PY, "build_site.py"])
    run([PY, "bump_assets.py"])
    run([PY, "check_site.py"])

    git("add", "--", *PATHS)
    added = titles_added()
    if not git("diff", "--cached", "--name-only").strip():
        raise Stop("匯入後檔案沒有任何變化，沒有東西可以上線")

    body = "\n".join(f"- {t}" for t in added)
    msg = (f"醫學新知：{'、'.join(dates)} 的每日摘要上線（{n} 篇）\n\n"
           f"{body}\n\n由 Telegram 指令觸發，publish_digest.py 執行。\n\n"
           "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>")
    git("commit", "-m", msg)
    git("push")

    sha = git("rev-parse", "--short", "HEAD").strip()
    print(f"✅ 已上線（{sha}）　{n} 篇")
    for t in added:
        print(f"　• {t}")
    print("\nGitHub Pages 通常 1–2 分鐘後生效："
          "https://kidneygod.net/articles/news.html")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as e:
        print(f"❌ {e}")
        sys.exit(1)
