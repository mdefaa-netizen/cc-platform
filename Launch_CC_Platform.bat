@echo off
title Community Conversations Platform
cd /d %~dp0
echo Starting Community Conversations Platform...
echo.
echo Once started, open your browser and go to:
echo    localhost:8501
echo.
echo Password: see .streamlit/secrets.toml (APP_PASSWORD)
echo.
python -m streamlit run app.py
pause
