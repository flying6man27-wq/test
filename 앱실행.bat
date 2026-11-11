@echo off
chcp 65001 > nul
cd /d %~dp0
echo 단타 트레이딩 화면을 여는 중입니다... (이 창을 닫으면 프로그램이 종료됩니다)
start "" cmd /c "timeout /t 4 > nul & start http://localhost:8501"
python -m streamlit run app.py
pause
