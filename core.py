#!/usr/bin/env python3
"""IELTS Camp 核心：資料庫、題庫載入、弱點引擎、選題演算法。全部離線，不呼叫任何 API。"""
import json
import math
import os
import random
import re
import sqlite3
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(BASE, "data", "bank")
DB_PATH = os.path.join(BASE, "data", "progress.db")

# 等級順序：由易到難
LEVEL_ORDER = ["J1", "J2", "J3", "H1", "H2", "H3", "IB"]
LEVEL_ZH = {
    "J1": "國一", "J2": "國二", "J3": "國三",
    "H1": "高一", "H2": "高二", "H3": "高三", "IB": "銜接雅思",
}
CEFR_BAND = {"A1": 3.5, "A2": 4.5, "B1": 5.5, "B2": 6.5, "B2+": 7.0}
SKILL_ZH = {
    "vocab": "字彙", "grammar": "文法", "cloze": "克漏字",
    "reading": "閱讀", "listening": "聽力", "phrase": "片語搭配",
}

# ---------------------------------------------------------------- 題庫


class Bank:
    def __init__(self):
        self.items = []
        self.by_id = {}
        self.load()

    def load(self):
        self.items, self.by_id = [], {}
        if not os.path.isdir(BANK_DIR):
            return
        for fn in sorted(os.listdir(BANK_DIR)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(BANK_DIR, fn), encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:  # 壞檔不要讓整個網站掛掉
                print(f"[題庫] 略過 {fn}: {e}")
                continue
            if not isinstance(data, list):
                continue
            for it in data:
                if not isinstance(it, dict) or "id" not in it:
                    continue
                if it["id"] in self.by_id:
                    continue
                it.setdefault("passage", None)
                it.setdefault("group_id", None)
                it.setdefault("vocab", [])
                self.items.append(it)
                self.by_id[it["id"]] = it

    def reload_all(self):
        self.load()
        DICT.load()

    def stats(self):
        by_level, by_skill, tags = {}, {}, set()
        for it in self.items:
            by_level[it.get("level", "?")] = by_level.get(it.get("level", "?"), 0) + 1
            by_skill[it.get("skill", "?")] = by_skill.get(it.get("skill", "?"), 0) + 1
            tags.add(it.get("tag", "?"))
        return {"total": len(self.items), "by_level": by_level,
                "by_skill": by_skill, "tags": len(tags)}


BANK = Bank()

# ---------------------------------------------------------------- 逐字翻譯

IRREGULAR = {
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be", "been": "be",
    "has": "have", "had": "have", "does": "do", "did": "do", "done": "do",
    "went": "go", "gone": "go", "made": "make", "took": "take", "taken": "take",
    "got": "get", "gotten": "get", "saw": "see", "seen": "see", "came": "come",
    "knew": "know", "known": "know", "thought": "think", "said": "say",
    "told": "tell", "found": "find", "gave": "give", "given": "give",
    "felt": "feel", "left": "leave", "put": "put", "brought": "bring",
    "bought": "buy", "caught": "catch", "taught": "teach", "wrote": "write",
    "written": "write", "read": "read", "ran": "run", "ate": "eat",
    "eaten": "eat", "drank": "drink", "spoke": "speak", "spoken": "speak",
    "broke": "break", "chose": "choose", "children": "child", "people": "person",
    "men": "man", "women": "woman", "feet": "foot", "teeth": "tooth",
    "better": "good", "best": "good", "worse": "bad", "worst": "bad",
    "more": "much", "most": "much",
}


class Dict_:
    """英翻中字典：資料來自 data/dict.json 加上題庫本身帶的翻譯欄位。"""

    def __init__(self):
        self.d = {}
        self.load()

    def _put(self, w, zh, pos=""):
        if not w or not zh:
            return
        k = str(w).strip().lower()
        if k and k not in self.d:
            self.d[k] = {"zh": str(zh).strip(), "pos": pos or ""}

    FILES = ("dict.json", "dict_core.json", "dict_adv.json",
             "dict_x1.json", "dict_x2.json", "dict_x3.json", "dict_extra.json",
             "dict_y1.json", "dict_y2.json", "dict_y3.json", "dict_y4.json",
             "dict_z1.json", "dict_z2.json", "dict_z3.json")

    def load(self):
        self.d = {}
        for fn in self.FILES:
            path = os.path.join(BASE, "data", fn)
            if not os.path.exists(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    for w, v in json.load(f).items():
                        if isinstance(v, dict):
                            self._put(w, v.get("zh"), v.get("pos", ""))
                        else:
                            self._put(w, v)
            except Exception as e:
                print(f"[字典] {fn} 讀取失敗:", e)
        for it in BANK.items:
            for v in it.get("vocab") or []:
                if isinstance(v, dict):
                    self._put(v.get("w"), v.get("zh"), v.get("pos", ""))
            for g in it.get("stem_gloss") or []:
                if isinstance(g, dict):
                    self._put(g.get("w"), g.get("zh"))
            og = it.get("options_gloss")
            if isinstance(og, list):
                for o, z in zip(it.get("options", []), og):
                    if isinstance(o, str) and " " not in o.strip():
                        self._put(o, z)

    def look(self, word):
        w = word.lower().strip("'")
        seen = set()
        for cand in self._forms(w):
            if cand in seen:
                continue
            seen.add(cand)
            if cand in self.d:
                return self.d[cand]["zh"]
            for b in self._british(cand):     # 變化形還原後再試英式拼法
                if b in self.d:
                    return self.d[b]["zh"]
        return None

    @staticmethod
    def _british(w):
        """英式拼法轉美式，讓字典只要收一種就夠。"""
        for a, b in (("ise", "ize"), ("ised", "ized"), ("ising", "izing"),
                     ("isation", "ization"), ("yse", "yze"), ("ysed", "yzed"),
                     ("our", "or"), ("ours", "ors"), ("ogue", "og"),
                     ("ence", "ense"), ("aeon", "eon")):
            if w.endswith(a):
                yield w[:-len(a)] + b
        if w.endswith("re") and len(w) > 4:
            yield w[:-2] + "er"            # centre -> center
        if w.endswith("res") and len(w) > 5:
            yield w[:-3] + "ers"
        if "ll" in w:
            yield w.replace("ll", "l", 1)  # travelled -> traveled
        if w.startswith("ae") or w.startswith("oe"):
            yield w[1:]

    @staticmethod
    def _forms(w):
        yield w
        for b in Dict_._british(w):
            yield b
        if w in IRREGULAR:
            yield IRREGULAR[w]
        if w.endswith("n't"):
            yield w[:-3]
        if w.endswith("'s") or w.endswith("'re") or w.endswith("'ll"):
            yield w.split("'")[0]
        for suf, subs in (("ies", ["y"]), ("ied", ["y"]), ("ier", ["y"]),
                          ("iest", ["y"]), ("es", ["", "e"]), ("s", [""]),
                          ("ed", ["", "e"]), ("ing", ["", "e"]),
                          ("er", ["", "e"]), ("est", ["", "e"]),
                          ("ly", [""]), ("'s", [""])):
            if w.endswith(suf) and len(w) > len(suf) + 1:
                stem = w[:-len(suf)]
                for sub in subs:
                    yield stem + sub
                if len(stem) > 2 and stem[-1] == stem[-2]:  # running -> run
                    for sub in subs:
                        yield stem[:-1] + sub


DICT = Dict_()

TOKEN_RE = re.compile(
    r"[A-Za-z]+(?:[-'][A-Za-z]+)+|[A-Za-z]+|_{2,}|[^A-Za-z\s]+|\s+")


def is_word(tok):
    """只有 2 個字母以上的英文字才需要查中文；單一字母（拼字題）與中文都不算。"""
    w = tok.get("w", "")
    return (not tok.get("sp")) and len(w) > 1 and w.isascii() and w[0].isalpha()


def _look_hyphen(w):
    """Wi-Fi、well-known 這類字整個查；查不到寧可不顯示，也不要拼出錯誤翻譯。"""
    z = DICT.look(w)
    if z:
        return z
    z = DICT.look(w.replace("-", ""))
    if z:
        return z
    # 逐段拼湊容易翻錯（well-known → 井-知道），所以查不到就不顯示
    return None


def gloss(text):
    """把一段英文切成 [{w, zh}]，每個單字附上中文；查不到的 zh 為 None。"""
    if not text:
        return []
    out = []
    for tok in TOKEN_RE.findall(str(text)):
        if tok.isspace():
            out.append({"w": " ", "zh": None, "sp": True})
        elif tok.isascii() and tok[0].isalpha():
            if len(tok) <= 1:
                z = None
            elif "-" in tok:
                z = _look_hyphen(tok)
            else:
                z = DICT.look(tok)
            out.append({"w": tok, "zh": z})
        else:
            out.append({"w": tok, "zh": None})
    return out


def gloss_coverage():
    """字典涵蓋率：題庫裡所有單字有多少比例查得到中文。"""
    total = hit = 0
    for it in BANK.items:
        for t in gloss(it.get("stem", "")):
            if not is_word(t):
                continue
            total += 1
            hit += 1 if t["zh"] else 0
    return {"words": total, "hit": hit,
            "pct": round(hit / total * 100) if total else 0,
            "dict_size": len(DICT.d)}

# ---------------------------------------------------------------- 資料庫

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
  k TEXT PRIMARY KEY, v TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, item_id TEXT, skill TEXT, tag TEXT, tag_zh TEXT,
  level TEXT, cefr TEXT, chosen INTEGER, correct INTEGER, seconds REAL,
  mode TEXT
);
CREATE TABLE IF NOT EXISTS review (
  item_id TEXT PRIMARY KEY, due TEXT, stage INTEGER, wrong_count INTEGER,
  last_ts TEXT
);
CREATE TABLE IF NOT EXISTS essays (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, kind TEXT, task TEXT, body TEXT, words INTEGER,
  band REAL, feedback TEXT
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, body TEXT
);
CREATE TABLE IF NOT EXISTS marks (
  item_id TEXT PRIMARY KEY, ts TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS daylog (
  day TEXT PRIMARY KEY, questions INTEGER, correct INTEGER, minutes REAL
);
"""


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with db() as c:
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM profile WHERE k='start_date'").fetchone():
            c.execute("INSERT INTO profile VALUES('start_date',?)",
                      (date.today().isoformat(),))
            c.execute("INSERT OR REPLACE INTO profile VALUES('level','J2')")
            c.execute("INSERT OR REPLACE INTO profile VALUES('target_band','6.5')")
            c.execute("INSERT OR REPLACE INTO profile VALUES('placed','0')")


def get_profile():
    with db() as c:
        rows = c.execute("SELECT k,v FROM profile").fetchall()
    p = {r["k"]: r["v"] for r in rows}
    p.setdefault("start_date", date.today().isoformat())
    p.setdefault("level", "J2")
    p.setdefault("target_band", "6.5")
    p.setdefault("placed", "0")
    return p


def set_profile(**kw):
    with db() as c:
        for k, v in kw.items():
            c.execute("INSERT OR REPLACE INTO profile VALUES(?,?)", (k, str(v)))


def day_index():
    p = get_profile()
    d0 = date.fromisoformat(p["start_date"])
    return (date.today() - d0).days + 1

# ---------------------------------------------------------------- 弱點引擎


def tag_stats(days=None):
    q = ("SELECT tag, tag_zh, skill, COUNT(*) n, SUM(correct) ok, "
         "SUM(CASE WHEN chosen=-1 THEN 1 ELSE 0 END) dk, "
         "MAX(ts) last FROM attempts")
    args = []
    if days:
        q += " WHERE ts >= ?"
        args.append((datetime.now() - timedelta(days=days)).isoformat())
    q += " GROUP BY tag"
    with db() as c:
        rows = c.execute(q, args).fetchall()
    out = []
    for r in rows:
        n, ok = r["n"], r["ok"] or 0
        acc = ok / n if n else 0
        # 弱點分數：錯越多、練越多次還是錯 → 分數越高
        score = (1 - acc) * math.log(1 + n) * 10
        out.append({"tag": r["tag"], "tag_zh": r["tag_zh"] or r["tag"],
                    "skill": r["skill"], "n": n, "ok": ok,
                    "acc": round(acc * 100), "score": round(score, 1),
                    "last": r["last"]})
    out.sort(key=lambda x: -x["score"])
    return out


def weak_tags(limit=8, min_n=2):
    return [t for t in tag_stats() if t["n"] >= min_n and t["acc"] < 80][:limit]


def level_window(level=None):
    """回傳可以出題的等級清單：目前等級 ±1 級。"""
    p = get_profile()
    lv = level or p["level"]
    if lv not in LEVEL_ORDER:
        lv = "J2"
    i = LEVEL_ORDER.index(lv)
    return LEVEL_ORDER[max(0, i - 1): i + 2]


def due_reviews(limit=50):
    today = date.today().isoformat()
    with db() as c:
        rows = c.execute(
            "SELECT item_id FROM review WHERE due<=? ORDER BY due LIMIT ?",
            (today, limit)).fetchall()
    return [r["item_id"] for r in rows if r["item_id"] in BANK.by_id]


def pick_items(n=10, skill=None, level=None, mode="mix", tag=None):
    """離線選題：40% 弱點標籤、25% 到期複習、35% 新題。"""
    if tag:
        pool = [it for it in BANK.items if it.get("tag") == tag]
        if pool:
            random.shuffle(pool)
            return pool[:n]
    levels = set(level_window(level))
    pool = [it for it in BANK.items
            if it.get("level") in levels and (not skill or it.get("skill") == skill)]
    if not pool:
        pool = [it for it in BANK.items if (not skill or it.get("skill") == skill)]
    if not pool:
        return []

    with db() as c:
        seen = {r["item_id"] for r in
                c.execute("SELECT DISTINCT item_id FROM attempts").fetchall()}

    chosen, used = [], set()

    def take(cands, k):
        random.shuffle(cands)
        for it in cands:
            if len(chosen) >= n or k <= 0:
                break
            if it["id"] in used:
                continue
            used.add(it["id"])
            chosen.append(it)
            k -= 1

    if mode != "new":
        wt = {t["tag"] for t in weak_tags(limit=10)}
        if wt:
            take([it for it in pool if it.get("tag") in wt], max(1, int(n * 0.4)))
        rev = [BANK.by_id[i] for i in due_reviews()
               if (not skill or BANK.by_id[i].get("skill") == skill)]
        take(rev, max(1, int(n * 0.25)))
    take([it for it in pool if it["id"] not in seen], n)
    take(list(pool), n)  # 題庫不夠就允許重複舊題
    random.shuffle(chosen)
    return chosen[:n]


def pick_reading_group(level=None):
    """抽一整組閱讀題（同一篇文章）。"""
    levels = set(level_window(level))
    groups = {}
    for it in BANK.items:
        if it.get("skill") == "reading" and it.get("group_id") and it.get("level") in levels:
            groups.setdefault(it["group_id"], []).append(it)
    if not groups:
        groups = {g: [it for it in BANK.items if it.get("group_id") == g]
                  for g in {it.get("group_id") for it in BANK.items
                            if it.get("skill") == "reading" and it.get("group_id")}}
    if not groups:
        return []
    with db() as c:
        seen = {r["item_id"] for r in
                c.execute("SELECT DISTINCT item_id FROM attempts").fetchall()}
    fresh = [g for g, its in groups.items() if any(i["id"] not in seen for i in its)]
    gid = random.choice(fresh or list(groups))
    return sorted(groups[gid], key=lambda x: x["id"])


def pick_listening(level=None):
    levels = set(level_window(level))
    pool = [it for it in BANK.items
            if it.get("skill") == "listening" and it.get("level") in levels]
    if not pool:
        pool = [it for it in BANK.items if it.get("skill") == "listening"]
    if not pool:
        return []
    groups = {}
    for it in pool:
        groups.setdefault(it.get("group_id") or it["id"], []).append(it)
    gid = random.choice(list(groups))
    return sorted(groups[gid], key=lambda x: x["id"])

# ---------------------------------------------------------------- 記錄作答


REVIEW_GAPS = [1, 3, 7, 16, 35]


DONT_KNOW = -1


def record(item, chosen, seconds=0.0, mode="drill"):
    """chosen 傳 -1 代表學生按了「我不會」：不算答對，但和猜錯分開記錄。"""
    it = BANK.by_id.get(item) if isinstance(item, str) else item
    if not it:
        return None
    correct = 1 if chosen == it.get("answer") else 0
    now = datetime.now().isoformat(timespec="seconds")
    with db() as c:
        c.execute(
            "INSERT INTO attempts(ts,item_id,skill,tag,tag_zh,level,cefr,"
            "chosen,correct,seconds,mode) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (now, it["id"], it.get("skill"), it.get("tag"), it.get("tag_zh"),
             it.get("level"), it.get("cefr"), chosen, correct, seconds, mode))
        row = c.execute("SELECT stage,wrong_count FROM review WHERE item_id=?",
                        (it["id"],)).fetchone()
        stage = row["stage"] if row else 0
        wrong = row["wrong_count"] if row else 0
        if correct:
            stage = min(stage + 1, len(REVIEW_GAPS) - 1)
            if row is None:
                stage = -1  # 第一次就對，不排複習
        else:
            stage, wrong = 0, wrong + 1
        if stage >= 0:
            due = (date.today() + timedelta(days=REVIEW_GAPS[stage])).isoformat()
            c.execute("INSERT OR REPLACE INTO review VALUES(?,?,?,?,?)",
                      (it["id"], due, stage, wrong, now))
        today = date.today().isoformat()
        c.execute("INSERT INTO daylog(day,questions,correct,minutes) VALUES(?,1,?,?) "
                  "ON CONFLICT(day) DO UPDATE SET questions=questions+1, "
                  "correct=correct+?, minutes=minutes+?",
                  (today, correct, seconds / 60, correct, seconds / 60))
    return correct


def mark_toggle(item_id, note=""):
    with db() as c:
        row = c.execute("SELECT 1 FROM marks WHERE item_id=?", (item_id,)).fetchone()
        if row:
            c.execute("DELETE FROM marks WHERE item_id=?", (item_id,))
            return False
        c.execute("INSERT INTO marks VALUES(?,?,?)",
                  (item_id, datetime.now().isoformat(timespec="seconds"), note))
        return True


def marked_ids():
    with db() as c:
        return [r["item_id"] for r in
                c.execute("SELECT item_id FROM marks ORDER BY ts DESC").fetchall()]


def marked_items():
    out = []
    with db() as c:
        rows = c.execute("SELECT item_id, ts, note FROM marks ORDER BY ts DESC").fetchall()
    for r in rows:
        it = BANK.by_id.get(r["item_id"])
        if it:
            out.append({**it, "marked_ts": r["ts"], "note": r["note"]})
    return out


def overall_stats():
    with db() as c:
        row = c.execute("SELECT COUNT(*) n, SUM(correct) ok FROM attempts").fetchone()
        today = c.execute(
            "SELECT questions,correct FROM daylog WHERE day=?",
            (date.today().isoformat(),)).fetchone()
        days = c.execute("SELECT day FROM daylog ORDER BY day DESC LIMIT 40").fetchall()
        wrong_n = c.execute(
            "SELECT COUNT(*) n FROM review WHERE wrong_count>0").fetchone()["n"]
        mark_n = c.execute("SELECT COUNT(*) n FROM marks").fetchone()["n"]
        dk = c.execute("SELECT COUNT(*) n FROM attempts WHERE chosen=?",
                       (DONT_KNOW,)).fetchone()["n"]
        by_skill = c.execute(
            "SELECT skill, COUNT(*) n, SUM(correct) ok FROM attempts "
            "GROUP BY skill").fetchall()
    streak, d = 0, date.today()
    dayset = {r["day"] for r in days}
    while d.isoformat() in dayset:
        streak += 1
        d -= timedelta(days=1)
    n, ok = row["n"] or 0, row["ok"] or 0
    return {
        "total": n, "correct": ok, "acc": round(ok / n * 100) if n else 0,
        "today_q": today["questions"] if today else 0,
        "today_ok": today["correct"] if today else 0,
        "streak": streak, "wrong_book": wrong_n, "marked": mark_n,
        "dontknow": dk, "guessed_wrong": max(0, n - ok - dk),
        "due": len(due_reviews(999)),
        "by_skill": [{"skill": r["skill"], "zh": SKILL_ZH.get(r["skill"], r["skill"]),
                      "n": r["n"], "acc": round((r["ok"] or 0) / r["n"] * 100)}
                     for r in by_skill],
    }


def estimate_band():
    """依最近 120 題的等級與正確率粗估目前實力（僅供參考）。"""
    with db() as c:
        rows = c.execute("SELECT cefr, correct FROM attempts ORDER BY id DESC "
                         "LIMIT 120").fetchall()
    if len(rows) < 15:
        return None
    tot = w = 0.0
    for r in rows:
        base = CEFR_BAND.get(r["cefr"], 5.0)
        tot += base + (0.6 if r["correct"] else -0.9)
        w += 1
    return round(max(3.0, min(8.0, tot / w)) * 2) / 2


def recent_wrongs(limit=60):
    with db() as c:
        rows = c.execute(
            "SELECT a.item_id, a.tag_zh, a.skill, MAX(a.ts) ts, r.wrong_count "
            "FROM attempts a LEFT JOIN review r ON r.item_id=a.item_id "
            "WHERE a.correct=0 GROUP BY a.item_id ORDER BY ts DESC LIMIT ?",
            (limit,)).fetchall()
    out = []
    for r in rows:
        it = BANK.by_id.get(r["item_id"])
        if it:
            out.append({**it, "wrong_count": r["wrong_count"] or 1, "ts": r["ts"]})
    return out


init_db()
