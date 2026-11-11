@echo off
chcp 65001 > nul
cd /d %~dp0
REM 매일 장 마감 후(16시 이후) 실행: 지난 결과 확인 -> 오늘 스캔 -> 대시보드(브라우저) 열기
python main.py track
python main.py scan
python main.py dashboard
echo.
echo 완료. 브라우저에 대시보드가 열렸습니다. 아무 키나 누르면 창이 닫힙니다.
pause > nul
