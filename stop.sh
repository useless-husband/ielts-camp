#!/bin/bash
cd "$(dirname "$0")"
if [ -f data/app.pid ]; then
  kill "$(cat data/app.pid)" 2>/dev/null && echo "已關閉"
  rm -f data/app.pid
else
  pkill -f "python app.py" && echo "已關閉" || echo "本來就沒在執行"
fi
