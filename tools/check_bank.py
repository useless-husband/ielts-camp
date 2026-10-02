#!/usr/bin/env python3
"""題庫檔驗證器：用法 python3 check_bank.py <file.json> [file2.json ...]"""
import json
import sys
from collections import Counter

SKILLS = {"vocab", "grammar", "cloze", "reading", "listening", "phrase"}
LEVELS = {"J1", "J2", "J3", "H1", "H2", "H3", "IB"}
CEFR = {"A1", "A2", "B1", "B2", "B2+"}


def check_file(path):
    errs = []
    with open(path, encoding="utf-8") as f:
        try:
            items = json.load(f)
        except Exception as e:
            return [f"JSON 解析失敗: {e}"], 0, Counter()
    if not isinstance(items, list):
        return ["最外層必須是 JSON 陣列"], 0, Counter()

    ids, stems = set(), set()
    ans_dist = Counter()
    for i, it in enumerate(items):
        w = f"[第{i+1}題]"
        if not isinstance(it, dict):
            errs.append(f"{w} 不是物件")
            continue
        for k in ("id", "level", "cefr", "skill", "tag", "tag_zh", "stem",
                  "options", "answer", "explain_zh"):
            if k not in it:
                errs.append(f"{w} 缺少欄位 {k}")
        if errs and any(f"{w} 缺少欄位" in e for e in errs[-10:]):
            continue
        if it["id"] in ids:
            errs.append(f"{w} id 重複: {it['id']}")
        ids.add(it["id"])
        s = " ".join(str(it["stem"]).split())
        if s in stems:
            errs.append(f"{w} 題幹重複: {s[:40]}")
        stems.add(s)
        if it["level"] not in LEVELS:
            errs.append(f"{w} level 不合法: {it['level']}")
        if it["cefr"] not in CEFR:
            errs.append(f"{w} cefr 不合法: {it['cefr']}")
        if it["skill"] not in SKILLS:
            errs.append(f"{w} skill 不合法: {it['skill']}")
        if ":" not in str(it["tag"]):
            errs.append(f"{w} tag 必須是 類別:細項 格式: {it['tag']}")
        o = it.get("options")
        if not isinstance(o, list) or len(o) != 4:
            errs.append(f"{w} options 必須剛好 4 個")
        elif len(set(map(str, o))) != 4:
            errs.append(f"{w} options 有重複")
        a = it.get("answer")
        if not isinstance(a, int) or not 0 <= a <= 3:
            errs.append(f"{w} answer 必須是 0~3 的整數")
        else:
            ans_dist[a] += 1
        if len(str(it.get("explain_zh", ""))) < 10:
            errs.append(f"{w} explain_zh 太短")
        if it["skill"] in ("reading", "listening"):
            if not it.get("passage"):
                errs.append(f"{w} {it['skill']} 題必須有 passage")
            if it["skill"] == "reading" and not it.get("group_id"):
                errs.append(f"{w} 閱讀題必須有 group_id")
        if "____" not in it["stem"] and it["skill"] in ("vocab", "grammar", "cloze", "phrase"):
            if "?" not in it["stem"]:
                errs.append(f"{w} 填空題題幹需含 ____ 或為問句")

    n = len(items)
    if n >= 30 and ans_dist:
        for k in range(4):
            share = ans_dist[k] / n
            if share < 0.15 or share > 0.35:
                errs.append(f"答案分布不均：選項 {k} 佔 {share:.0%}（應在 15%~35%）")
    return errs, n, ans_dist


def main():
    total, bad = 0, 0
    for path in sys.argv[1:]:
        errs, n, dist = check_file(path)
        total += n
        if errs:
            bad += 1
            print(f"✗ {path}（{n} 題）")
            for e in errs[:40]:
                print("   -", e)
            if len(errs) > 40:
                print(f"   ... 還有 {len(errs)-40} 個問題")
        else:
            print(f"✓ {path}：{n} 題，答案分布 {dict(sorted(dist.items()))}")
    print(f"\n合計 {total} 題，{'OK' if bad == 0 else f'{bad} 個檔案有問題'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
