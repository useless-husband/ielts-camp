#!/usr/bin/env python3
"""90 天課表：本機產生，不用 AI。依你的起始等級自動調整前幾週的份量。"""
from datetime import date, timedelta

import core

# 12 週主軸（第 13 週的 6 天用來做總複習與模考）
WEEKS = [
    {"theme": "把國中文法地基補回來", "grammar": "be 動詞、一般動詞、現在／過去簡單式",
     "vocab": "日常生活 200 字", "focus": "vocab", "level": "J1"},
    {"theme": "時態全家福", "grammar": "進行式、未來式、現在完成式",
     "vocab": "學校與家庭 200 字", "focus": "grammar", "level": "J2"},
    {"theme": "句子變長的第一步", "grammar": "連接詞、不定詞與動名詞",
     "vocab": "食衣住行 200 字", "focus": "grammar", "level": "J2"},
    {"theme": "描述與比較", "grammar": "形容詞副詞、比較級最高級、介系詞",
     "vocab": "情緒與個性 200 字", "focus": "vocab", "level": "J3"},
    {"theme": "國中總驗收＋讀短文", "grammar": "國中文法綜合複習",
     "vocab": "國中 2000 字漏網之魚", "focus": "cloze", "level": "J3"},
    {"theme": "關係子句上手", "grammar": "關係代名詞、關係副詞、限定與非限定",
     "vocab": "科技與媒體 200 字", "focus": "grammar", "level": "H1"},
    {"theme": "被動與名詞子句", "grammar": "被動語態、that／wh- 名詞子句",
     "vocab": "環境與永續 200 字", "focus": "grammar", "level": "H1"},
    {"theme": "假設語氣與分詞", "grammar": "三種條件句、分詞構句",
     "vocab": "教育與工作 200 字", "focus": "reading", "level": "H2"},
    {"theme": "學術閱讀技巧", "grammar": "倒裝、強調句、同位語",
     "vocab": "學術高頻字 AWL 前 300", "focus": "reading", "level": "H2"},
    {"theme": "聽力抓重點", "grammar": "口語常見結構與連接語",
     "vocab": "雅思聽力場景字（校園、租屋、旅遊）", "focus": "listening", "level": "H3"},
    {"theme": "寫作起步：Task 2 架構", "grammar": "論說文句型與轉折語",
     "vocab": "論證與數據用語", "focus": "writing", "level": "H3"},
    {"theme": "口說與總整合", "grammar": "口說常用時態切換與拉長答案技巧",
     "vocab": "Part 2 描述人事時地物", "focus": "speaking", "level": "IB"},
]

# 每天的固定任務模板（分鐘數）
DAILY = {
    "vocab": [("字彙練習 20 題", 20), ("錯題複習", 10), ("聽力短文 1 篇", 15)],
    "grammar": [("文法練習 20 題", 20), ("錯題複習", 10), ("閱讀 1 篇", 20)],
    "cloze": [("克漏字 15 題", 20), ("字彙 10 題", 10), ("聽力短文 1 篇", 15)],
    "reading": [("閱讀 2 篇", 30), ("字彙 10 題", 10), ("錯題複習", 10)],
    "listening": [("聽力 2 段（含跟讀）", 30), ("文法 10 題", 10), ("錯題複習", 10)],
    "writing": [("寫作 1 題＋AI 批改", 40), ("文法 10 題", 10), ("錯題複習", 10)],
    "speaking": [("口說 2 題＋AI 批改", 30), ("字彙 10 題", 10), ("聽力 1 段", 15)],
}
REST = [("輕鬆複習錯題本", 15), ("看一支英文影片不查字典", 15)]


def start_week_index():
    """程度越好，前面補基礎的週數越少。"""
    lv = core.get_profile().get("level", "J2")
    return {"J1": 0, "J2": 1, "J3": 3, "H1": 5, "H2": 7, "H3": 8, "IB": 9}.get(lv, 1)


def build():
    p = core.get_profile()
    d0 = date.fromisoformat(p["start_date"])
    skip = start_week_index()
    weeks = WEEKS[skip:] + WEEKS[-1:] * 0
    # 若跳過前面幾週，後段加重複習週，總長固定 13 週
    while len(weeks) < 13:
        weeks.append({"theme": "弱點強化與模考", "grammar": "依你的錯題自動加強",
                      "vocab": "錯題本關鍵字", "focus": "reading", "level": "IB"})
    weeks = weeks[:13]

    out, day = [], 1
    for wi, w in enumerate(weeks, 1):
        days = []
        for di in range(7):
            the_date = d0 + timedelta(days=day - 1)
            rest = (di == 6)
            tasks = REST if rest else DAILY[w["focus"]]
            days.append({
                "day": day, "date": the_date.isoformat(),
                "weekday": "一二三四五六日"[the_date.weekday()],
                "rest": rest,
                "tasks": [{"title": t, "minutes": m} for t, m in tasks],
                "minutes": sum(m for _, m in tasks),
            })
            day += 1
        out.append({"week": wi, **w, "days": days,
                    "start": days[0]["date"], "end": days[-1]["date"]})
    return out


def today_tasks():
    d = core.day_index()
    for w in build():
        for day in w["days"]:
            if day["day"] == d:
                return w, day
    return None, None
