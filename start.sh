#!/bin/bash
# 啟動雅思特訓營
cd "$(dirname "$0")"
if [ -f data/app.pid ] && kill -0 "$(cat data/app.pid)" 2>/dev/null; then
  echo "已經在執行中了（PID $(cat data/app.pid)）"
else
  nohup ./venv/bin/python app.py > data/app.log 2>&1 &
  echo $! > data/app.pid
  sleep 2
fi
echo "網址： http://127.0.0.1:8790"
open http://127.0.0.1:8790
