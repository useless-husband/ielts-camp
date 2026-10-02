# 雅思特訓營 IELTS Camp

> **IELTS Camp** is a self-hosted, offline English training system that takes a learner from junior-high-school English to IELTS 6.5 in about 90 days. It runs as a local Flask app on your Mac: a 6,007-question bank (including 1,304 official Taiwanese past-exam items), a weakness-tracking engine, spaced-repetition review, placement test, 90-day study plan, reading and listening drills with per-word Chinese glosses, and AI essay/speaking feedback through your locally installed Claude Code CLI (no API key needed). The interface and all explanations are in Traditional Chinese.

從國中英文打底，三個月練到雅思 6.5。全部跑在你自己的 Mac 上，刷題完全離線；只有寫作、口說批改與「答題時問 AI」才會用到 Claude。

這是第一版（port 8790）。以「每日一課」為核心、附 Mac／iPhone App 的第二版在 [ielts-pro2](https://github.com/useless-husband/ielts-pro2)。

## 功能

- **分級測驗**：30 題定位你現在的程度（國一～銜接雅思七級），自動調整題目難度與課表
- **弱點引擎**：每題帶一個弱點標籤（例如 `grammar:present-perfect`），記錄每個標籤的正確率。出題時四成從你最弱的標籤抽、兩成半是到期要複習的、其餘才是新題
- **錯題本與間隔複習**：錯題照 1、3、7、16、35 天自動排複習；「我不會」和「猜錯」分開記錄
- **逐字中文**：題目、選項、文章裡每個英文字都點得出中文，預設隱藏，按 `Z` 整句顯示
- **閱讀、聽力、克漏字、片語**：聽力用 macOS 內建的英式語音朗讀，可調語速
- **90 天課表**：13 週，前 5 週補國中地基、6～9 週高中長句與學術閱讀、10～13 週聽說讀寫整合
- **寫作與口說 AI 批改**：雅思四項分數、逐條改錯、5 組「你的講法 → 高分講法」、一段 7 分示範、接下來最該練的 3 件事
- **AI 弱點診斷報告**與**答題時直接發問**（「為什麼不能選 B？」）
- **標記、統計、弱點分析頁**

## 題庫規模

| 項目 | 數量 |
|---|---|
| 選擇題 | 6,007 題（87 個 JSON 檔） |
| 其中歷屆真題 | 1,304 題（國中會考 103～115 年、大學學測 103～115 年、指考 103～110 年） |
| 等級 | 國一、國二、國三、高一、高二、高三、銜接雅思（CEFR A1～B2+） |
| 技能 | 字彙 1,409、文法 1,465、閱讀 1,411、聽力 790、克漏字 520、片語 412 |
| 弱點標籤 | 244 個 |
| 寫作題 / 口說題 | 40 篇 Task 2 / 60 題 Part 1～3 |
| 英翻中字典 | 約 9,800 字（逐字翻譯用） |

每一題都有繁體中文解析與關鍵字。題目格式見 [data/題庫規格.md](data/題庫規格.md)。

## 安裝與啟動

需要 macOS 與 Python 3.9 以上。

```bash
git clone https://github.com/useless-husband/ielts-camp.git
cd ielts-camp
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./start.sh
```

`start.sh` 會在背景啟動伺服器並打開 <http://127.0.0.1:8790>；關閉用 `./stop.sh`。電腦重開後再跑一次 `start.sh` 即可。
也可以在 Finder 裡對 `start.sh` 連按兩下。

第一次使用：首頁點「開始分級測驗」，30 題約 10 分鐘，做完系統會自動排好之後的難度與課表。每天打開首頁看「今天的任務」照著做就好，約 45 分鐘。詳細操作、鍵盤快速鍵與常見問題見 [使用說明.md](使用說明.md)。

### AI 功能（選用）

刷題、閱讀、聽力、錯題本、課表、統計完全離線，不需要 AI。寫作批改、口說批改、弱點診斷報告與答題時發問需要以下其一：

- 已安裝並登入 [Claude Code](https://claude.com/claude-code)：程式會呼叫本機的 `claude` 指令（`~/.local/bin/claude` 或 `PATH` 裡找得到的），用你現有的 Claude 方案，不需要 API 金鑰
- 或設定環境變數 `ANTHROPIC_API_KEY`：自動改用官方 Anthropic SDK

模型可用環境變數 `IELTS_AI_MODEL` 更換。

### 聽力語音

聽力用 macOS 的 `say` 指令朗讀。建議到「系統設定 → 輔助使用 → 朗讀內容 → 系統聲音 → 管理聲音」下載英式語音 Daniel；沒有的話會用系統預設聲音。

## 專案結構

```
app.py              Flask 伺服器與所有路由
core.py             題庫載入、弱點引擎、逐字翻譯字典、作答紀錄（SQLite）
plan.py             90 天課表
ai.py               AI 批改與發問（claude CLI 或 Anthropic SDK）
templates/ static/  網頁介面
data/bank/          題庫（每個 JSON 是一批題目）
data/prompts.json   寫作與口說題目
data/dict*.json     英翻中字典
data/題庫規格.md     題目 JSON 格式
tools/              題庫驗證、缺字檢查、答案抽查工具
使用說明.md          每天怎麼用、快速鍵、常見問題
```

執行後會自動產生、不在 repo 裡的檔案：`data/progress.db`（你的作答紀錄）、`data/app.log`、`static/audio/`（聽力音檔快取）。想從頭開始就把 `data/progress.db` 刪掉再重開。

## 自己加題目

在 `data/bank/` 放一個新的 JSON 檔，格式見 [data/題庫規格.md](data/題庫規格.md)，然後驗證：

```bash
./venv/bin/python tools/check_bank.py data/bank/你的檔案.json
./venv/bin/python tools/missing_words.py        # 看有沒有字典查不到的字
```

缺的字補進 `data/dict_extra.json`，再開 <http://127.0.0.1:8790/api/reload> 重新載入，不用重開程式。

## 關於題目來源

- **會考、學測、指考歷屆試題**取自國中教育會考官網與大學入學考試中心公開的試題與答案。依《著作權法》第 9 條第 1 項第 5 款，依法令舉行之各類考試試題不得為著作權之標的。解析為本專案自行撰寫。
- **雅思題目**全部是依真實題型撰寫的仿真題，不含劍橋官方出版的 IELTS 真題。
- 其餘題目、解析、字典與寫作範文由 AI 協助撰寫，並經自動驗證與抽樣人工核對；如發現錯誤歡迎開 Issue。

## 關於開發

本專案由 [Claude Code](https://claude.com/claude-code) 協助開發。

## 授權

[MIT](LICENSE)
