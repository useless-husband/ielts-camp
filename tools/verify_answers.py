#!/usr/bin/env python3
"""答案正確性抽查：隨機抽題送給 AI 覆核，找出標錯答案或有兩個答案的題目。

用法：python3 tools/verify_answers.py [抽查題數] [--file 檔名]
"""
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ai      # noqa: E402
import core    # noqa: E402

BATCH = 10

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string",
                                "enum": ["ok", "wrong_key", "ambiguous", "bad_item"]},
                    "correct_index": {"type": "integer"},
                    "reason_zh": {"type": "string"},
                },
                "required": ["id", "verdict", "correct_index", "reason_zh"],
            },
        }
    },
    "required": ["results"],
}

SYSTEM = (
    "你是嚴格的英文考題審查員。針對每一題判斷標準答案是否正確。"
    "verdict 只能是四種：ok（標準答案正確且只有一個答案）、"
    "wrong_key（標準答案標錯了，correct_index 填正確的索引）、"
    "ambiguous（有兩個以上選項都說得通）、bad_item（題目本身有文法或語意錯誤）。"
    "correct_index 一律填你認為正確的選項索引（0~3）。"
    "reason_zh 用繁體中文一句話說明；判定 ok 時 reason_zh 寫「正確」即可。"
    "請嚴格但不要吹毛求疵，正常的教學用題目就算 ok。只輸出 JSON。"
)


def check(items):
    lines = []
    for it in items:
        opts = " | ".join(f"{i}={o}" for i, o in enumerate(it["options"]))
        ctx = f"（文章：{it['passage'][:400]}）" if it.get("passage") else ""
        lines.append(f"id={it['id']}\n題目：{it['stem']}{ctx}\n選項：{opts}\n"
                     f"標準答案索引：{it['answer']}")
    return ai.ask("請逐題審查：\n\n" + "\n\n".join(lines), SCHEMA, SYSTEM,
                  effort="medium")["results"]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 60
    pool = core.BANK.items
    if "--file" in sys.argv:
        f = sys.argv[sys.argv.index("--file") + 1]
        pre = os.path.basename(f).split(".")[0]
        pool = [i for i in pool if i["id"].startswith(pre)]
    sample = random.sample(pool, min(n, len(pool)))
    bad = []
    for i in range(0, len(sample), BATCH):
        chunk = sample[i:i + BATCH]
        try:
            for r in check(chunk):
                if r["verdict"] != "ok":
                    bad.append(r)
                    print(f"  ⚠ {r['id']} [{r['verdict']}] {r['reason_zh']}")
        except ai.AIError as e:
            print("  （這批審查失敗：", e, "）")
        print(f"已審查 {min(i + BATCH, len(sample))}/{len(sample)}，發現 {len(bad)} 個問題")
    print(f"\n抽查 {len(sample)} 題，可疑 {len(bad)} 題"
          f"（{len(bad) / len(sample) * 100:.1f}%）")
    if bad:
        out = os.path.join(os.path.dirname(__file__), "..", "data", "verify_report.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(bad, f, ensure_ascii=False, indent=1)
        print("詳細報告：data/verify_report.json")


if __name__ == "__main__":
    main()
