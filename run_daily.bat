@echo off
REM 매일 장 마감 후(예: 16:00) 실행. Windows 작업 스케줄러에 등록하면 자동화됩니다.
chcp 65001 > nul
cd /d %~dp0
python main.py track
python main.py scan
