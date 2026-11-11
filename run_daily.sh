#!/usr/bin/env bash
# 매일 장 마감 후(예: 16:00) 실행. cron 예: 0 16 * * 1-5 /path/to/run_daily.sh >> daily.log 2>&1
cd "$(dirname "$0")"
python3 main.py track
python3 main.py scan
