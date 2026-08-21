# -*- coding: utf-8 -*-
"""產生 60 張中央插圖的生圖 prompt，給 Gemini（或其他生圖服務）用。

畫好的圖存成 gi/art/{id}.png，make_gi_cards.py 會自動改用外部插圖，
不必改任何程式碼。插圖區是 780x432（約 16:9），出圖請用 16:9。

寫 prompt 的原則：
  ・畫的是「概念的象徵」，不是器官寫實圖 —— 衛教卡不該讓人不適
  ・不要有文字：生圖模型寫中文幾乎必錯，卡面上的字由程式排版
  ・每張都指定深色底，跟卡面的分類色一致，整套才會像同一副牌
"""
import os, sys, json

sys.stdout.reconfigure(encoding="utf-8")

STYLE = ("Flat vector illustration in the style of a 1990s Japanese trading card. "
         "Bold confident outlines, limited flat colour palette, subtle halftone dot "
         "texture, dramatic light rays radiating from the centre. Single centred "
         "subject with generous margins. Clean graphic poster look, no gradients "
         "on skin, no photorealism, no gore. "
         "ABSOLUTELY NO text, letters, numbers, words, logos or watermarks anywhere.")

BG = {
    "血壓管理": "deep crimson red background",
    "血糖管理": "deep amber brown background",
    "血脂代謝": "deep olive gold background",
    "檢查數值": "deep indigo blue background",
    "用藥安全": "deep navy blue background",
    "飲食護腎": "deep teal green background",
    "生活習慣": "deep steel blue background",
    "警訊與迷思": "deep wine red background",
}

# id → 畫面內容（英文，具體可畫）
SCENE = {
 # ── 血壓管理 ──
 "bp-acei": "A glowing bean-shaped kidney with a small brass pressure-relief valve on its side, "
            "gently venting soft light; two tiny protein droplets drift away and dissolve.",
 "bp-stop": "A hand reaching toward a pill bottle whose cap is half open, while behind it a large "
            "gauge needle silently creeps back up into the red zone.",
 "bp-130": "A large ornate pressure dial seen head-on, its needle resting just below a clearly marked "
           "threshold notch, with a downward arrow sweeping across the face.",
 "bp-ckd": "A kidney surrounded by three closed taps and rising water, one tap straining under pressure "
           "while salt crystals swirl in the current.",
 "bp-salt": "A tiny salt shaker in the foreground dwarfed by an enormous looming bowl of noodle soup and "
            "stacked packaged snacks casting a long shadow.",
 "bp-whitecoat": "Split composition: on one side a figure sitting stiffly in a clinic chair, on the other "
                 "the same figure relaxed at a desk; two opposing gauge needles between them.",
 "bp-722": "A home upper-arm blood pressure monitor on a wooden table, a seven-column calendar grid "
           "glowing faintly behind it, morning sun and evening moon at either side.",
 "bp-night": "A crescent moon over a sleeping city skyline, with a luminous line that should dip at night "
             "but stays stubbornly flat and high.",
 "bp-silent": "A calm featureless human silhouette, serene on the outside, with a single pressure gauge "
              "glowing hidden deep inside the chest.",
 "bp-howto": "An arm resting on a table with a cuff correctly placed at heart level, feet flat on the floor, "
             "clean geometric alignment guides drawn around the posture.",

 # ── 血糖管理 ──
 "dm-fine": "Three playing cards fanned out, the third one being placed down and glowing brighter than the "
            "other two, a small kidney crest embossed on its face.",
 "dm-no1": "A podium with a single tall first-place step, a sugar cube standing on top of it, casting a long "
           "shadow over a distant dialysis-style spiral of tubing.",
 "dm-sglt2": "A kidney acting as a sluice gate, releasing a bright stream of sugar crystals safely out and "
             "away, with a heart shape glowing protected in the background.",
 "dm-a1c": "A report card shaped like a stained-glass panel divided into three month-segments, a red blood "
           "cell motif repeated across it.",
 "dm-glp1": "A single arrow splitting into three ribbons that curve toward a sugar cube, a scale, and a heart "
            "with a small kidney beside it.",
 "dm-keep": "A bridge held up by pillars made of capsules; one pillar being removed and the bridge deck "
            "beginning to sag at that point.",
 "dm-met": "A classic balance scale with a tablet on one pan and a small kidney on the other, the beam "
           "carefully levelled by an adjusting hand.",
 "dm-screen": "A wall calendar with two dates circled and glowing, a urine sample vial and a blood tube "
              "standing beside it like sentries.",
 "dm-uacr": "A long ascending staircase with two landings marked by tall stone gateposts, a single droplet "
            "climbing from the bottom step.",
 "dm-hypo": "A candle flame guttering dangerously low inside a glass lantern, a sugar cube and a glass of "
            "juice placed urgently beside it.",

 # ── 血脂代謝 ──
 "lp-ldl": "An archery target where the bullseye ring is drawn at a different radius for each of several "
           "overlapping targets, one arrow already embedded in the innermost.",
 "ms-kidney": "Three rivers coloured red, amber and gold converging into one delta that flows into a large "
              "bean-shaped kidney basin.",
 "lp-muscle": "A flexed arm rendered as layered flat muscle bands, one band glowing warm with irritation, a "
              "small warning lantern hanging nearby.",
 "lp-statin": "A cross-section of a pipe with a waxy plaque deposit inside being sealed under a smooth "
              "protective glaze, calm flow continuing through.",
 "lp-tg": "Oil droplets clustering thickly in a stream, and downstream a pancreas-shaped island beginning "
          "to glow hot red as an alarm.",
 "ms-cluster": "Three interlocking rings, red amber and gold, chained together and all anchored to one "
               "central weight below.",
 "ms-def": "Five lanterns hanging in a row, exactly three of them lit and glowing, the other two dark.",
 "ms-unaware": "A crowd of simple silhouettes, most with a small dim warning light floating unnoticed above "
               "their heads, one figure just beginning to look up.",
 "lp-hdl": "A delivery cart carrying waxy cargo away from a pipe, drawn as helpful but ordinary, with a "
           "rising arrow that flattens out at the top instead of continuing upward.",
 "ms-waist": "A measuring tape wrapped around a rounded abdomen shape, the tape trailing off toward a small "
             "kidney silhouette on the horizon.",

 # ── 檢查數值 ──
 "egfr": "A large circular dial marked into descending zones, a bean-shaped kidney at its centre and a "
         "needle resting in the upper zone.",
 "hba1c": "A sugar cube dissolving inside a glass vial while a faint kidney outline behind it slowly dims.",
 "bp": "Two interlocked gears, one shaped like a pressure gauge and one like a kidney, grinding against "
       "each other with sparks between the teeth.",
 "proteinuria": "A stream of fine dense bubbles rising in a tall glass vessel, one bubble magnified to "
                "reveal a tiny protein crystal inside.",
 "echo": "A fan-shaped ultrasound beam sweeping across a bean-shaped kidney, the swept area rendered as "
         "clean concentric arcs of light.",

 # ── 用藥安全 ──
 "nsaid": "A white capsule with a bold diagonal warning slash across it, and behind it three converging "
          "arrows striking a single kidney shape.",
 "aristo": "A dried herbal root in an apothecary jar, its shadow on the wall shaped like a cracked kidney "
           "that cannot be repaired, a broken chain link nearby.",
 "unknown-med": "A plain unlabelled paper packet spilling mismatched pills of wildly different shapes and "
                "colours, each one a question of its own.",
 "contrast": "A syringe of luminous contrast fluid beside a small card held up to a scanner ring, a kidney "
             "glowing gently as it is checked first.",
 "abx": "A row of capsules laid out as a complete course, the row fully filled to the end, with a shield "
        "standing over the last one.",
 "ppi": "A comfortable armchair made of stomach-medicine tablets, sitting on a foundation that is quietly "
        "cracking beneath it.",

 # ── 飲食護腎 ──
 "protein": "A balance scale with a steak and eggs on one pan and a small kidney on the other, both pans "
            "hovering at exactly equal height.",
 "phosphate": "A packaged sausage and a fizzy drink can, each leaking a stream of tiny crystals that settle "
              "and harden along a length of pipe.",
 "starfruit": "A single star-shaped fruit slice glowing with an ominous aura, sealed behind a crossed "
              "barrier, dark leaves around it.",
 "uricacid": "Sharp needle-like crystals radiating from a swollen big toe joint, with the same crystals "
             "quietly settling inside a kidney silhouette behind.",
 "potassium": "A banana and leafy greens on a set of scales, perfectly fine on one side, while on the other "
              "side a heart rhythm line shows a single dangerous tall spike.",
 "salt": "A mop and bucket beside an enormous spilled mound of salt, a small kidney figure dutifully "
         "cleaning it up, looking tired.",
 "sportsdrink": "A sports drink bottle tipped over, pouring out not liquid but a cascade of sugar cubes, an "
                "untouched glass of plain water standing calmly beside it.",
 "water": "A glass of water raised in the foreground, and behind it a heart with a small restriction band "
          "and a dialysis spiral, both marked as exceptions.",

 # ── 生活習慣 ──
 "smoking": "A lit cigarette whose smoke curls into narrowing blood vessels that constrict as they reach a "
            "kidney shape in the distance.",
 "dehydration": "A cracked dry riverbed leading to a kidney-shaped basin nearly empty, a single precious "
                "water droplet falling from above.",
 "dietpill": "A slot machine whose reels show pills, a diuretic droplet and a question mark shape, with a "
             "kidney sitting where the payout tray should be.",
 "exercise": "A running figure in mid-stride, three coloured rings for pressure, sugar and lipid shrinking "
             "in their wake, a kidney glowing steadily.",
 "sleep": "A crescent moon and a pillow, while behind them a kidney sits at a small desk under a lamp, "
          "still working through the night.",
 "holdurine": "A dam holding back rising water far past its limit, with a narrow channel leading upward "
              "toward a kidney at the top of the valley.",

 # ── 警訊與迷思 ──
 "dialysis-myth": "A pointing finger aimed at a bottle of prescription tablets, but the actual long shadow "
                  "on the ground is cast by an untreated pressure gauge and a sugar cube.",
 "five-signs": "Five lanterns hanging in a row, each carrying a distinct simple symbol: bubbles, a swollen "
               "foot, a gauge, a pale droplet, and a drooping figure.",
 "edema": "A thumb pressing into the front of a lower leg, leaving a clear round dent that stays behind "
          "after the thumb lifts away.",
 "backpain": "A figure clutching the lower back, with the spine and muscle layers glowing as the real "
             "source, while a small kidney behind sits quietly unlit.",
 "organ-food": "A steaming bowl of braised offal on a table, its rising steam forming sharp uric acid "
               "crystals and phosphate specks instead of aroma.",
}


def main():
    data = json.load(open("knowledge_export.json", encoding="utf-8"))
    order = ["血壓管理", "血糖管理", "血脂代謝", "檢查數值",
             "用藥安全", "飲食護腎", "生活習慣", "警訊與迷思"]
    data.sort(key=lambda x: (order.index(x["cat"]), -x["price"], x["id"]))

    missing = [x["id"] for x in data if x["id"] not in SCENE]
    if missing:
        print("⚠ 尚未寫畫面描述:", missing); return

    os.makedirs("gi/art", exist_ok=True)
    out, jsn = [], {}
    out.append("護腎教室 — Greed Island 風格卡片｜中央插圖 生圖 Prompt（共 60 張）")
    out.append("=" * 78)
    out.append("用法：每一段整段複製丟給 Gemini，出圖比例選 16:9，")
    out.append("      存成 gi/art/<檔名>.png，再執行 python make_gi_cards.py 即可換上。")
    out.append("插圖區實際尺寸 780x432 px，出圖大一點沒關係，程式會置中裁切。")
    out.append("=" * 78)
    out.append("")

    cur = None
    for i, x in enumerate(data, 1):
        if x["cat"] != cur:
            cur = x["cat"]
            out += ["", f"■■■ {cur} ■■■", ""]
        p = f"{STYLE} {BG[x['cat']]}. {SCENE[x['id']]}"
        jsn[x["id"]] = p
        out.append(f"── {i:02d}. {x['title']}")
        out.append(f"   檔名：gi/art/{x['id']}.png")
        out.append(f"   Prompt：{p}")
        out.append("")

    open("GI插圖_Gemini_Prompt.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
    json.dump(jsn, open("gi/prompts.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"完成 {len(jsn)} 段 prompt → GI插圖_Gemini_Prompt.txt / gi/prompts.json")


if __name__ == "__main__":
    main()
