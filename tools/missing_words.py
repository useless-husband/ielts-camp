#!/usr/bin/env python3
"""找出題庫裡字典查不到中文的單字，依出現次數排序。
用法：python3 tools/missing_words.py [輸出檔.txt] [每檔上限]"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402


def main():
    miss = Counter()
    for it in core.BANK.items:
        texts = [it.get("stem", "")] + list(it.get("options") or [])
        if it.get("passage"):
            texts.append(it["passage"])
        for t in texts:
            for tok in core.gloss(t):
                if not core.is_word(tok):
                    continue
                if not tok["zh"]:
                    miss[tok["w"].lower()] += 1
    out = sys.argv[1] if len(sys.argv) > 1 else None
    words = [w for w, _ in miss.most_common()]
    print(f"題庫 {len(core.BANK.items)} 題，字典 {len(core.DICT.d)} 字，"
          f"查不到 {len(words)} 個不同單字（共 {sum(miss.values())} 次）")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(f"{w}\t{miss[w]}" for w in words))
        print("已寫出：", out)
    else:
        print("前 40 個：", ", ".join(words[:40]))


if __name__ == "__main__":
    main()
