@echo off
chcp 65001 > nul
cd /d %~dp0
echo 이전에 켜져 있던 단타 트레이딩 프로그램이 있으면 종료합니다...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8501" ^| findstr "LISTENING"') do taskkill /F /PID %%a > nul 2>&1
timeout /t 1 > nul
echo 단타 트레이딩 화면을 여는 중입니다... (이 창을 닫으면 프로그램이 종료됩니다)
start "" cmd /c "timeout /t 5 > nul & start http://localhost:8501"
python -m streamlit run app.py
pause
