#!/usr/bin/env python3
"""AI 批改與分析：透過本機 claude CLI，用你現有的 Claude Code 登入，不需要 API 金鑰。

平常刷題完全不會用到這個檔案，只有按「AI 批改作文／口說」或「產生弱點報告」才會呼叫。
"""
import json
import os
import shutil
import subprocess

CLAUDE = shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")
DEFAULT_MODEL = os.environ.get("IELTS_AI_MODEL", "claude-opus-5")
TIMEOUT = 420

try:
    import anthropic
except ImportError:
    anthropic = None


class AIError(Exception):
    pass


def _sdk_client():
    """只有在設了 ANTHROPIC_API_KEY 時才走官方 SDK；否則回 None 改用本機 claude 指令。"""
    if anthropic is None or not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


def backend():
    if _sdk_client():
        return "sdk"
    if CLAUDE and os.path.exists(CLAUDE):
        return "cli"
    return None


def available():
    return backend() is not None


def _strict(schema):
    """轉成 structured outputs 要求的嚴格 schema：所有欄位必填、不准多餘欄位。"""
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if out.get("type") == "object":
        props = {k: _strict(v) for k, v in out.get("properties", {}).items()}
        out["properties"] = props
        out["required"] = list(props)
        out["additionalProperties"] = False
    if out.get("type") == "array" and "items" in out:
        out["items"] = _strict(out["items"])
    return out


def _ask_sdk(client, prompt, schema, system, model, effort):
    kw = dict(
        model=model, max_tokens=16000, system=system,
        messages=[{"role": "user", "content": prompt}],
        thinking={"type": "adaptive"},
        output_config={"effort": effort,
                       "format": {"type": "json_schema", "schema": _strict(schema)}},
    )
    try:
        try:
            r = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
        except anthropic.BadRequestError:
            r = client.messages.create(**kw)   # 這個環境不支援 fallback 就照常送
    except anthropic.AuthenticationError:
        raise AIError("API 金鑰無效，請檢查 ANTHROPIC_API_KEY。")
    except anthropic.RateLimitError:
        raise AIError("被限流了，等一下再按一次。")
    except anthropic.APIStatusError as e:
        raise AIError(f"API 錯誤 {e.status_code}：{str(e)[:200]}")
    except anthropic.APIConnectionError:
        raise AIError("連不上 Anthropic，請檢查網路。")
    if r.stop_reason == "refusal":
        raise AIError("這個內容 AI 拒絕處理，換一題試試。")
    if r.stop_reason == "max_tokens":
        raise AIError("回覆被截斷了，請再試一次。")
    text = next((b.text for b in r.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise AIError("AI 回傳的不是合法 JSON，請再試一次。")


def ask(prompt, schema, system, model=None, effort="high"):
    """要求 AI 回傳符合 schema 的 JSON。有 API 金鑰走官方 SDK，否則走本機 claude 指令。"""
    model = model or DEFAULT_MODEL
    client = _sdk_client()
    if client:
        return _ask_sdk(client, prompt, schema, system, model, effort)
    if not (CLAUDE and os.path.exists(CLAUDE)):
        raise AIError("找不到 claude 指令，AI 功能無法使用（刷題不受影響）。")
    cmd = [
        CLAUDE, "-p", prompt,
        "--system-prompt", system,
        "--json-schema", json.dumps(schema, ensure_ascii=False),
        "--output-format", "json",
        "--model", model,
        "--effort", effort,
        "--tools", "",
        "--no-session-persistence",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise AIError("AI 回應逾時，請再試一次。")
    if r.returncode != 0:
        raise AIError((r.stderr or r.stdout or "claude 執行失敗")[-400:])
    try:
        env = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise AIError("AI 回傳格式看不懂，請再試一次。")
    if env.get("is_error"):
        raise AIError(str(env.get("result"))[:400])
    out = env.get("structured_output")
    if out is None:
        try:
            out = json.loads(env.get("result", ""))
        except Exception:
            raise AIError("AI 沒有回傳結構化結果，請再試一次。")
    return out


# --------------------------------------------------------------- 作文批改

ESSAY_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_band": {"type": "number"},
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_zh": {"type": "string"},
                    "band": {"type": "number"},
                    "comment_zh": {"type": "string"},
                },
                "required": ["name_zh", "band", "comment_zh"],
            },
        },
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "corrected": {"type": "string"},
                    "tag": {"type": "string"},
                    "tag_zh": {"type": "string"},
                    "explain_zh": {"type": "string"},
                },
                "required": ["original", "corrected", "tag_zh", "explain_zh"],
            },
        },
        "upgrade_phrases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "plain": {"type": "string"},
                    "better": {"type": "string"},
                    "zh": {"type": "string"},
                },
                "required": ["plain", "better", "zh"],
            },
        },
        "model_paragraph": {"type": "string"},
        "next_focus_zh": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["overall_band", "criteria", "errors", "next_focus_zh"],
}

ESSAY_SYSTEM = (
    "你是資深雅思寫作考官兼台灣學生的英文家教。嚴格按照 IELTS Writing 公版評分標準"
    "（Task Response、Coherence and Cohesion、Lexical Resource、"
    "Grammatical Range and Accuracy）給分，分數用 0.5 為單位。"
    "所有說明一律用繁體中文、台灣用語，語氣鼓勵但誠實，不要灌分。"
    "errors 只挑最關鍵的 6～10 個錯誤，tag 用英文小寫連字號（例如 grammar:article、"
    "vocab:word-choice），tag_zh 用中文短語。只輸出 JSON。"
)


def grade_essay(kind, task, body, target="6.5"):
    prompt = (
        f"學生目標分數：{target}\n"
        f"題型：{kind}\n題目：{task}\n\n"
        f"學生作文（{len(body.split())} 字）：\n---\n{body}\n---\n\n"
        "請給四項分數與總分、指出關鍵錯誤並改正、提供 5 組『平凡講法 → 高分講法』、"
        "改寫其中一段成 7 分水準的示範段落（model_paragraph），"
        "最後列出接下來 3 件最該練的事。"
    )
    return ask(prompt, ESSAY_SCHEMA, ESSAY_SYSTEM)


# --------------------------------------------------------------- 口說批改

SPEAK_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_band": {"type": "number"},
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_zh": {"type": "string"},
                    "band": {"type": "number"},
                    "comment_zh": {"type": "string"},
                },
                "required": ["name_zh", "band", "comment_zh"],
            },
        },
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "corrected": {"type": "string"},
                    "tag_zh": {"type": "string"},
                    "explain_zh": {"type": "string"},
                },
                "required": ["original", "corrected", "tag_zh", "explain_zh"],
            },
        },
        "upgrade_phrases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "plain": {"type": "string"},
                    "better": {"type": "string"},
                    "zh": {"type": "string"},
                },
                "required": ["plain", "better", "zh"],
            },
        },
        "model_answer": {"type": "string"},
        "next_focus_zh": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["overall_band", "criteria", "errors", "next_focus_zh"],
}

SPEAK_SYSTEM = (
    "你是資深雅思口說考官。依 Fluency and Coherence、Lexical Resource、"
    "Grammatical Range and Accuracy、Pronunciation 四項評分（0.5 為單位）。"
    "學生給的是逐字稿，發音項目只能依用字選擇與句子節奏合理推測，並在評語中說明這點。"
    "所有說明用繁體中文、台灣用語。model_answer 寫一段 7 分水準、口語自然、"
    "40～90 字的示範回答。只輸出 JSON。"
)


def grade_speaking(part, question, transcript, target="6.5"):
    prompt = (
        f"學生目標分數：{target}\n口說 {part}\n題目：{question}\n\n"
        f"學生逐字稿：\n---\n{transcript}\n---\n\n"
        "請評分、挑出關鍵錯誤並改正、給 5 組升級講法、寫一段示範回答、"
        "列出接下來 3 件最該練的事。"
    )
    return ask(prompt, SPEAK_SCHEMA, SPEAK_SYSTEM)


# --------------------------------------------------------------- 弱點分析

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_zh": {"type": "string"},
        "estimated_band": {"type": "number"},
        "weak_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tag_zh": {"type": "string"},
                    "why_zh": {"type": "string"},
                    "rule_zh": {"type": "string"},
                    "example_en": {"type": "string"},
                    "drill_zh": {"type": "string"},
                },
                "required": ["tag_zh", "why_zh", "rule_zh", "drill_zh"],
            },
        },
        "strengths_zh": {"type": "array", "items": {"type": "string"}},
        "next_7_days": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "day": {"type": "string"},
                    "focus_zh": {"type": "string"},
                    "tasks_zh": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["day", "focus_zh", "tasks_zh"],
            },
        },
    },
    "required": ["summary_zh", "weak_points", "next_7_days"],
}

REPORT_SYSTEM = (
    "你是專門帶台灣學生從國中程度衝到雅思 6.5 的英文教練。"
    "根據學生的答題統計寫一份具體、可執行的弱點診斷。"
    "全部用繁體中文、台灣用語。weak_points 最多 6 項，每項要說清楚『觀念規則』"
    "並附一個英文例句；drill_zh 要是今天就能做的具體動作（含題數或分鐘數）。"
    "next_7_days 剛好 7 天，每天 2～3 個任務、總時數不超過 90 分鐘。只輸出 JSON。"
)


def weekly_report(stats, tags, wrong_samples, day, target="6.5", level_zh=""):
    lines = [f"目前是第 {day} 天，目標 {target} 分，目前程度約：{level_zh}",
             f"累積作答 {stats['total']} 題，正確率 {stats['acc']}%",
             "各技能正確率：" + "、".join(
                 f"{s['zh']} {s['acc']}%（{s['n']} 題）" for s in stats["by_skill"]),
             "", "最弱的標籤（標籤／練習題數／正確率）："]
    for t in tags[:12]:
        dk = f"，其中 {t['dk']} 題直接按『我不會』" if t.get("dk") else ""
        lines.append(f"- {t['tag_zh']}（{t['tag']}）：{t['n']} 題，正確率 {t['acc']}%{dk}")
    lines.append("\n注意：學生按『我不會』代表完全沒概念，比猜錯更需要從頭教觀念；"
                 "請在 weak_points 裡優先處理這些標籤。")
    if wrong_samples:
        lines.append("\n最近答錯的題目範例：")
        for w in wrong_samples[:12]:
            lines.append(
                f"- [{w.get('tag_zh')}] {w.get('stem')} ｜正解：{w['options'][w['answer']]}")
    return ask("\n".join(lines), REPORT_SCHEMA, REPORT_SYSTEM)


# --------------------------------------------------------------- 即時問答

QA_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_zh": {"type": "string"},
        "rule_zh": {"type": "string"},
        "examples": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "en": {"type": "string"},
                    "zh": {"type": "string"},
                },
                "required": ["en", "zh"],
            },
        },
        "remember_zh": {"type": "string"},
    },
    "required": ["answer_zh", "rule_zh", "examples", "remember_zh"],
}

QA_SYSTEM = (
    "你是台灣學生的英文家教，學生程度大約國中到高中，正在準備雅思。"
    "學生會針對他剛剛做的一道題目問你問題。請用繁體中文、台灣用語，"
    "講得像在旁邊教他一樣：先直接回答他問的，再說清楚背後的規則，"
    "然後給 2～3 個簡單好懂的英文例句（每句都要附中文），"
    "最後給一句好記的口訣或判斷方法。不要長篇大論，不要用艱深術語。只輸出 JSON。"
)


def ask_question(item, question, chosen=None):
    """學生針對某一題即時發問。"""
    opts = "\n".join(f"  {'ABCD'[i]}. {o}" for i, o in enumerate(item.get("options", [])))
    lines = [
        f"題目：{item.get('stem')}",
        f"選項：\n{opts}",
        f"正確答案：{'ABCD'[item.get('answer', 0)]}. "
        f"{item.get('options', [''])[item.get('answer', 0)]}",
        f"這題的考點：{item.get('tag_zh')}（{item.get('tag')}）",
        f"原本的解析：{item.get('explain_zh')}",
    ]
    if item.get("passage"):
        lines.append(f"文章／聽力稿：\n{item['passage']}")
    if chosen is not None and 0 <= chosen < len(item.get("options", [])):
        lines.append(f"學生選的是：{'ABCD'[chosen]}. {item['options'][chosen]}")
    lines.append(f"\n學生的問題：{question}")
    return ask("\n".join(lines), QA_SCHEMA, QA_SYSTEM, effort="medium")
