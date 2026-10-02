#!/usr/bin/env python3
"""IELTS Camp 雅思特訓營 —— 本機離線英文訓練系統。

啟動：./start.sh  然後在瀏覽器開 http://127.0.0.1:8790
"""
import hashlib
import json
import os
import random
import re
import subprocess
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request, send_from_directory

import ai
import core
import plan as planner

BASE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE, "static", "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

FALLBACK_PROMPTS = {
    "writing": [{
        "kind": "Task 2", "topic_zh": "教育",
        "task": ("Some people think that children should start learning a foreign "
                 "language at primary school, while others believe it is better to "
                 "start at secondary school. Discuss both views and give your own "
                 "opinion."),
        "words": 250, "minutes": 40,
    }],
    "speaking": [{
        "part": "Part 1", "topic_zh": "家鄉",
        "question": "Where do you live now? What do you like about it?",
        "seconds": 45,
    }],
}


def load_prompts():
    path = os.path.join(BASE, "data", "prompts.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("writing") and d.get("speaking"):
                return d
        except Exception as e:
            print("[prompts] 讀取失敗:", e)
    return FALLBACK_PROMPTS


def _MARKS():
    return set(core.marked_ids())


def clean_item(it, reveal=False, marks=None):
    """送到前端的題目；未作答前不給答案與解析。"""
    marks = _MARKS() if marks is None else marks
    out = {k: it.get(k) for k in
           ("id", "level", "cefr", "skill", "tag", "tag_zh", "stem", "options",
            "group_id")}
    out["skill_zh"] = core.SKILL_ZH.get(it.get("skill"), it.get("skill"))
    out["level_zh"] = core.LEVEL_ZH.get(it.get("level"), it.get("level"))
    out["stem_g"] = core.gloss(it.get("stem", ""))
    out["opts_g"] = [core.gloss(o) for o in it.get("options", [])]
    out["marked"] = it["id"] in marks
    if it.get("skill") in ("reading", "cloze") and it.get("passage"):
        out["passage"] = it.get("passage")
        out["passage_g"] = core.gloss(it.get("passage"))
    if reveal:
        out["answer"] = it.get("answer")
        out["explain_zh"] = it.get("explain_zh")
        out["vocab"] = it.get("vocab")
    return out


# ------------------------------------------------------------------ 頁面

@app.route("/")
def home():
    st = core.overall_stats()
    week, today = planner.today_tasks()
    return render_template(
        "home.html", st=st, p=core.get_profile(), day=core.day_index(),
        week=week, today=today, bank=core.BANK.stats(),
        weak=core.weak_tags(limit=6), band=core.estimate_band(),
        level_zh=core.LEVEL_ZH.get(core.get_profile()["level"], ""),
        ai_ok=ai.available())


@app.route("/drill")
def drill():
    tag = request.args.get("tag", "")
    tag_zh = next((i.get("tag_zh") for i in core.BANK.items if i.get("tag") == tag), tag)
    return render_template("drill.html", skill=request.args.get("skill", ""),
                           n=int(request.args.get("n", 10)),
                           skills=core.SKILL_ZH, tag=tag, tag_zh=tag_zh)


@app.route("/reading")
def reading():
    return render_template("reading.html")


@app.route("/listening")
def listening():
    return render_template("listening.html")


@app.route("/writing")
def writing():
    pr = load_prompts()["writing"]
    with core.db() as c:
        rows = c.execute("SELECT id,ts,kind,task,words,band FROM essays "
                         "WHERE kind LIKE 'Task%' ORDER BY id DESC LIMIT 20").fetchall()
    return render_template("writing.html", prompts=pr, history=[dict(r) for r in rows],
                           ai_ok=ai.available())


@app.route("/speaking")
def speaking():
    pr = load_prompts()["speaking"]
    with core.db() as c:
        rows = c.execute("SELECT id,ts,kind,task,words,band FROM essays "
                         "WHERE kind LIKE 'Part%' ORDER BY id DESC LIMIT 20").fetchall()
    return render_template("speaking.html", prompts=pr, history=[dict(r) for r in rows],
                           ai_ok=ai.available())


@app.route("/wrongs")
def wrongs():
    return render_template("wrongs.html", items=core.recent_wrongs(80),
                           due=len(core.due_reviews(999)))


@app.route("/report")
def report():
    with core.db() as c:
        rows = c.execute("SELECT id,ts FROM reports ORDER BY id DESC LIMIT 10").fetchall()
        last = c.execute("SELECT body FROM reports ORDER BY id DESC LIMIT 1").fetchone()
    return render_template("report.html", tags=core.tag_stats(),
                           st=core.overall_stats(), ai_ok=ai.available(),
                           history=[dict(r) for r in rows],
                           last=json.loads(last["body"]) if last else None)


@app.route("/plan")
def plan_page():
    return render_template("plan.html", weeks=planner.build(), day=core.day_index(),
                           p=core.get_profile())


@app.route("/placement")
def placement():
    return render_template("placement.html")


@app.route("/essay/<int:eid>")
def essay_detail(eid):
    with core.db() as c:
        row = c.execute("SELECT * FROM essays WHERE id=?", (eid,)).fetchone()
    if not row:
        return "找不到這篇", 404
    fb = json.loads(row["feedback"]) if row["feedback"] else None
    return render_template("essay.html", e=dict(row), fb=fb)


# ------------------------------------------------------------------ API

@app.route("/api/items")
def api_items():
    mode = request.args.get("mode", "drill")
    n = min(int(request.args.get("n", 10)), 40)
    skill = request.args.get("skill") or None

    if mode == "placement":
        items = []
        for lv, k in (("J1", 4), ("J2", 5), ("J3", 5), ("H1", 6), ("H2", 5),
                      ("H3", 3), ("IB", 2)):
            pool = [i for i in core.BANK.items
                    if i.get("level") == lv and i.get("skill") in
                    ("vocab", "grammar", "cloze", "phrase")]
            random.shuffle(pool)
            items += pool[:k]
        mk = _MARKS()
        return jsonify([clean_item(i, marks=mk) for i in items])

    if mode == "review":
        ids = core.due_reviews(n)
        items = [core.BANK.by_id[i] for i in ids]
        if len(items) < n:
            items += core.pick_items(n - len(items), skill=skill)
    elif mode == "marked":
        items = [core.BANK.by_id[i] for i in core.marked_ids()
                 if i in core.BANK.by_id][:n]
    elif mode == "wrongbook":
        items = [w for w in core.recent_wrongs(n)]
    else:
        items = core.pick_items(n, skill=skill, tag=request.args.get("tag") or None)
    mk = _MARKS()
    return jsonify([clean_item(i, marks=mk) for i in items])


@app.route("/api/reading")
def api_reading():
    g = core.pick_reading_group()
    if not g:
        return jsonify({"error": "題庫還沒有閱讀題"}), 404
    return jsonify({"passage": g[0].get("passage"),
                    "level_zh": core.LEVEL_ZH.get(g[0].get("level"), ""),
                    "items": [clean_item(i, marks=_MARKS()) for i in g]})


@app.route("/api/listening")
def api_listening():
    g = core.pick_listening()
    if not g:
        return jsonify({"error": "題庫還沒有聽力題"}), 404
    gid = g[0].get("group_id") or g[0]["id"]
    return jsonify({"audio": f"/api/tts/{gid}",
                    "script": g[0].get("passage"),
                    "level_zh": core.LEVEL_ZH.get(g[0].get("level"), ""),
                    "items": [clean_item(i, marks=_MARKS()) for i in g]})


SPELL_RE = re.compile(r"\b(?:[A-Za-z]-){1,14}[A-Za-z]\b")
PHONE_RE = re.compile(r"\b\d[\d\s-]{6,}\d\b")


def _speakable(script):
    """把聽力稿轉成適合 say 唸的文字：
    去掉 A: B: 說話者標記、字母拼寫一個一個唸、電話號碼逐位唸。"""
    def spell(m):
        return " ".join(f"{c.upper()} [[slnc 140]]" for c in m.group(0) if c.isalpha())

    def digits(m):
        return " ".join(f"{c} [[slnc 120]]" for c in m.group(0) if c.isdigit())

    text = SPELL_RE.sub(spell, script)
    text = PHONE_RE.sub(digits, text)
    text = re.sub(r"^\s*([A-Z])\s*[:：]\s*", "[[slnc 550]] ", text, flags=re.M)
    return text.replace("\n", " [[slnc 380]] ")


def _script_for(gid):
    for it in core.BANK.items:
        if (it.get("group_id") or it.get("id")) == gid and it.get("passage"):
            return it["passage"]
    return None


@app.route("/api/tts/<gid>")
def api_tts(gid):
    """用 macOS 內建 say 產生英式發音音檔，第一次產生後就快取起來。"""
    script = _script_for(gid)
    if not script:
        return "找不到聽力稿", 404
    name = hashlib.md5((gid + script).encode()).hexdigest() + ".m4a"
    path = os.path.join(AUDIO_DIR, name)
    if not os.path.exists(path):
        text = _speakable(script)
        rate = request.args.get("rate", "160")
        try:
            subprocess.run(
                ["say", "-v", "Daniel", "-r", str(int(rate)), "-o", path,
                 "--data-format=aac", text],
                check=True, capture_output=True, timeout=120)
        except Exception as e:
            return f"產生音檔失敗：{e}", 500
    return send_from_directory(AUDIO_DIR, name, mimetype="audio/mp4")


@app.route("/api/answer", methods=["POST"])
def api_answer():
    d = request.get_json(force=True)
    it = core.BANK.by_id.get(d.get("id"))
    if not it:
        return jsonify({"error": "題目不存在"}), 404
    chosen = d.get("chosen")
    if chosen is None or not isinstance(chosen, int) or not -1 <= chosen <= 3:
        return jsonify({"error": "選項不合法"}), 400
    correct = core.record(it, chosen, float(d.get("seconds", 0)),
                          d.get("mode", "drill"))
    return jsonify({"correct": bool(correct),
                    "dontknow": chosen == core.DONT_KNOW,
                    "answer": it["answer"],
                    "explain_zh": it.get("explain_zh"), "vocab": it.get("vocab", []),
                    "options_gloss": it.get("options_gloss"),
                    "followup_zh": it.get("followup_zh")})


@app.route("/api/placement", methods=["POST"])
def api_placement():
    """依分級測驗結果推算起始等級。"""
    d = request.get_json(force=True)
    by_level = {}
    for r in d.get("results", []):
        it = core.BANK.by_id.get(r.get("id"))
        if not it:
            continue
        lv = it.get("level")
        s = by_level.setdefault(lv, [0, 0])
        s[0] += 1
        s[1] += 1 if r.get("correct") else 0
    level = "J1"
    for lv in core.LEVEL_ORDER:
        n, ok = by_level.get(lv, [0, 0])
        if n and ok / n >= 0.6:
            level = lv
    core.set_profile(level=level, placed=1, start_date=date.today().isoformat())
    return jsonify({"level": level, "level_zh": core.LEVEL_ZH[level],
                    "detail": {k: v for k, v in by_level.items()}})


@app.route("/api/grade", methods=["POST"])
def api_grade():
    d = request.get_json(force=True)
    kind = d.get("kind", "Task 2")
    task = d.get("task", "")
    body = (d.get("body") or "").strip()
    if len(body.split()) < 20:
        return jsonify({"error": "至少寫 20 個英文字再送出批改喔"}), 400
    target = core.get_profile().get("target_band", "6.5")
    try:
        if kind.startswith("Part"):
            fb = ai.grade_speaking(kind, task, body, target)
        else:
            fb = ai.grade_essay(kind, task, body, target)
    except ai.AIError as e:
        return jsonify({"error": str(e)}), 500
    band = float(fb.get("overall_band") or 0)
    with core.db() as c:
        cur = c.execute(
            "INSERT INTO essays(ts,kind,task,body,words,band,feedback) "
            "VALUES(?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), kind, task, body,
             len(body.split()), band, json.dumps(fb, ensure_ascii=False)))
        eid = cur.lastrowid
    return jsonify({"id": eid, "feedback": fb})


@app.route("/api/report", methods=["POST"])
def api_report():
    st = core.overall_stats()
    if st["total"] < 20:
        return jsonify({"error": "至少先做滿 20 題，分析才有意義"}), 400
    try:
        rep = ai.weekly_report(
            st, core.tag_stats(), core.recent_wrongs(14), core.day_index(),
            core.get_profile().get("target_band", "6.5"),
            core.LEVEL_ZH.get(core.get_profile()["level"], ""))
    except ai.AIError as e:
        return jsonify({"error": str(e)}), 500
    with core.db() as c:
        c.execute("INSERT INTO reports(ts,body) VALUES(?,?)",
                  (datetime.now().isoformat(timespec="seconds"),
                   json.dumps(rep, ensure_ascii=False)))
    return jsonify(rep)


@app.route("/api/mark", methods=["POST"])
def api_mark():
    d = request.get_json(force=True)
    iid = d.get("id")
    if iid not in core.BANK.by_id:
        return jsonify({"error": "題目不存在"}), 404
    on = core.mark_toggle(iid, d.get("note", ""))
    return jsonify({"marked": on, "total": len(core.marked_ids())})


@app.route("/api/ask", methods=["POST"])
def api_ask():
    d = request.get_json(force=True)
    it = core.BANK.by_id.get(d.get("id"))
    if not it:
        return jsonify({"error": "題目不存在"}), 404
    q = (d.get("question") or "").strip()
    if len(q) < 2:
        return jsonify({"error": "請先打出你的問題"}), 400
    try:
        ans = ai.ask_question(it, q, d.get("chosen"))
    except ai.AIError as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(ans)


@app.route("/marks")
def marks_page():
    items = core.marked_items()
    for it in items:
        it["_g"] = core.gloss(it.get("stem", ""))
    return render_template("marks.html", items=items)


@app.route("/api/gloss")
def api_gloss():
    return jsonify(core.gloss(request.args.get("t", "")))


@app.route("/api/settings", methods=["POST"])
def api_settings():
    d = request.get_json(force=True)
    kw = {}
    if d.get("level") in core.LEVEL_ORDER:
        kw["level"] = d["level"]
    if d.get("target_band"):
        kw["target_band"] = d["target_band"]
    if d.get("start_date"):
        kw["start_date"] = d["start_date"]
    if kw:
        core.set_profile(**kw)
    return jsonify(core.get_profile())


@app.route("/api/stats")
def api_stats():
    return jsonify({"stats": core.overall_stats(), "tags": core.tag_stats(),
                    "bank": core.BANK.stats(), "band": core.estimate_band()})


@app.route("/api/reload")
def api_reload():
    core.BANK.reload_all()
    return jsonify({**core.BANK.stats(), "gloss": core.gloss_coverage()})


if __name__ == "__main__":
    s = core.BANK.stats()
    print(f"題庫載入完成：{s['total']} 題，{s['tags']} 個弱點標籤")
    print("打開瀏覽器： http://127.0.0.1:8790")
    app.run(host="127.0.0.1", port=8790, debug=False, threaded=True)
