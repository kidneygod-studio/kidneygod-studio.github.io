# -*- coding: utf-8 -*-
"""呼叫 Gemini 生圖 API。用法：python gemini_img.py <模型> <輸出檔> <提示檔>"""
import os, sys, json, base64, urllib.request

sys.stdout.reconfigure(encoding="utf-8")

def get_key():
    k = os.environ.get("GEMINI_API_KEY")
    if k: return k
    p = os.path.expanduser("~/.claude/settings.json")
    return json.load(open(p, encoding="utf-8"))["env"]["GEMINI_API_KEY"]

def gen(model, prompt, out, aspect="4:5"):
    key = get_key()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect},
        },
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.load(r)
    cands = d.get("candidates") or []
    if not cands:
        print("NO_CANDIDATES:", json.dumps(d, ensure_ascii=False)[:500]); return False
    for part in cands[0].get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline:
            open(out, "wb").write(base64.b64decode(inline["data"]))
            print(f"OK {out} {os.path.getsize(out)//1024} KB")
            return True
        if part.get("text"):
            print("TEXT:", part["text"][:300])
    print("NO_IMAGE"); return False

if __name__ == "__main__":
    model, out, pfile = sys.argv[1], sys.argv[2], sys.argv[3]
    aspect = sys.argv[4] if len(sys.argv) > 4 else "4:5"
    gen(model, open(pfile, encoding="utf-8").read(), out, aspect)
