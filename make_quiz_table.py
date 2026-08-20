# -*- coding: utf-8 -*-
"""從 quiz.js 產生題庫對照表，方便逐題核對醫學實證來源。

不用單一大正則去吃整個物件（括號一多就難維護也容易寫壞），改成逐字掃描
JS 字串字面值：遇到 key 就從冒號後的引號開始讀到未跳脫的結尾引號為止。
這樣選項裡出現的逗號、括號、全形符號都不會影響解析。
"""
import sys, re, json
from collections import OrderedDict

sys.stdout.reconfigure(encoding="utf-8")
SRC_FILE = "quiz.js"
OUT = "小學堂題庫對照表.txt"


def read_str(s, i):
    """s[i] 必須是開頭的雙引號，回傳（內容, 結尾引號後的位置）。"""
    assert s[i] == '"', s[i:i+20]
    i += 1
    buf = []
    while s[i] != '"':
        if s[i] == "\\":
            buf.append(s[i:i+2]); i += 2
        else:
            buf.append(s[i]); i += 1
    return json.loads('"' + "".join(buf) + '"'), i + 1


def field(block, key):
    m = re.search(r'(?:^|[\s,{])' + key + r'\s*:\s*', block)
    if not m:
        return None
    i = m.end()
    if block[i] == '"':
        return read_str(block, i)[0]
    if block[i] == "[":
        out, i = [], i + 1
        while True:
            while block[i] in " \n\t,":
                i += 1
            if block[i] == "]":
                return out
            v, i = read_str(block, i)
            out.append(v)
    return int(re.match(r"\d+", block[i:]).group())


def main():
    src = open(SRC_FILE, encoding="utf-8").read()

    srcs = OrderedDict()
    body = re.search(r"const QUIZ_SRC = \{(.*?)\n\};", src, re.S).group(1)
    for k, v in re.findall(r'"([^"]+)":\s*"([^"]+)"', body):
        srcs[k] = v

    bank = src[src.index("const QUIZ = ["):src.index("const QUIZ_SRC")]
    blocks = re.split(r"\n\{(?=c:)", bank)[1:]
    qs = []
    for b in blocks:
        b = "{" + b.split("\n];")[0]
        qs.append({k: field(b, k) for k in ("c", "k", "q", "o", "a", "e", "src")})

    bad = [q for q in qs if not q["q"] or len(q["o"] or []) != 4
           or not isinstance(q["a"], int) or q["src"] not in srcs]
    if bad:
        print(f"⚠ 有 {len(bad)} 題結構異常:", [q["q"] for q in bad][:3]); return

    cats = list(OrderedDict.fromkeys(q["c"] for q in qs))
    L = [f"護腎小學堂 題庫對照表（共 {len(qs)} 題）",
         "本表供審閱用：每題附正解、解說與所依據的臨床指引，請逐題確認實證正確性。",
         "=" * 74, ""]
    n = 0
    for c in cats:
        sub = [q for q in qs if q["c"] == c]
        L += [f"■ {c}（{len(sub)} 題）", "-" * 74, ""]
        for q in sub:
            n += 1
            L.append(f"{n:>3}. {q['q']}")
            for i, o in enumerate(q["o"]):
                L.append(f"      {'✔' if i == q['a'] else ' '} {'ABCD'[i]}. {o}")
            L += [f"      解說：{q['e']}",
                  f"      依據：{srcs[q['src']]}",
                  f"      知識卡：{q['k']}", ""]
        L.append("")

    L += ["=" * 74, "來源清單：", ""]
    used = {q["src"] for q in qs}
    for k, v in srcs.items():
        cnt = sum(1 for q in qs if q["src"] == k)
        L.append(f"  {k}（{cnt} 題）　{v}")
    if used != set(srcs):
        L.append(f"  ※ 未被引用的來源：{set(srcs) - used}")

    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    from collections import Counter
    print(f"完成 {OUT}｜{len(qs)} 題")
    print("分類:", dict(Counter(q["c"] for q in qs)))
    print("來源:", dict(Counter(q["src"] for q in qs)))


if __name__ == "__main__":
    main()
