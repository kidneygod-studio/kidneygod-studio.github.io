# -*- coding: utf-8 -*-
r"""每日新知自動發佈到護腎教室網站（kidneygod.net / GitHub Pages）。

由 nephrology 每日摘要 runner 在報告生成成功後呼叫。管線：

    import_digests.py --write     把所有尚未匯入的每日摘要收進 news.json
    （若 news.json 沒變動 → 沒有新東西，直接結束，不 build 不 push）
    build_site.py                 news.json → articles/news*.html 等
    bump_assets.py                更新快取版本號
    check_site.py                 驗證；**沒過就不 push**（不發佈壞掉的站）
    git add -A && commit && push   發佈到 GitHub Pages

刻意不加 --only：import 以 DOI 去重，跑全部＝自動補上前幾天沒發佈成功的。
所以某天 push 失敗，隔天成功時會一起補上，具自我修復性。

Exit 0 = 已發佈或沒有新東西；非 0 = 某一步失敗（呼叫端會警報）。
"""
import subprocess, sys, os, datetime

ROOT = r'C:\Users\user\dopamine_shop'
PY   = sys.executable
# 讓 git 在無憑證時「快速失敗」而非卡在互動提示（無人值守必備）
ENV  = dict(os.environ, GIT_TERMINAL_PROMPT='0')


def run_py(args):
    return subprocess.run([PY] + args, cwd=ROOT, capture_output=True,
                          text=True, encoding='utf-8', errors='replace')


def git(args):
    return subprocess.run(['git'] + args, cwd=ROOT, capture_output=True,
                          text=True, encoding='utf-8', errors='replace', env=ENV)


def main():
    # 1. 匯入所有尚未進站的每日摘要
    r = run_py(['import_digests.py', '--write'])
    sys.stdout.write((r.stdout or '')[-1500:])
    if r.returncode != 0:
        print('IMPORT FAILED:', (r.stderr or '')[-500:]); return 1

    # 2. 沒有任何檔案變動 → 沒有新研究，收工
    if not git(['status', '--porcelain']).stdout.strip():
        print('nothing new to publish.'); return 0

    # 3. 重建網站
    b = run_py(['build_site.py'])
    if b.returncode != 0:
        print('BUILD FAILED:', (b.stderr or '')[-500:]); return 1
    run_py(['bump_assets.py'])

    # 4. 驗證；沒過就不發佈
    c = run_py(['check_site.py'])
    if c.returncode != 0:
        print('CHECK FAILED — not pushing:\n' + (c.stdout or '')[-1000:]); return 2

    # 5. 發佈
    git(['add', '-A'])
    date = datetime.date.today().strftime('%Y-%m-%d')
    msg = (f'每日新知自動發佈 {date}\n\n'
           f'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')
    if git(['commit', '-q', '-m', msg]).returncode != 0:
        print('COMMIT FAILED'); return 1
    p = git(['push', 'origin', 'main'])
    if p.returncode != 0:
        print('PUSH FAILED:', (p.stderr or '')[-500:]); return 3
    print(f'published {date} to kidneygod.net')
    return 0


if __name__ == '__main__':
    sys.exit(main())
