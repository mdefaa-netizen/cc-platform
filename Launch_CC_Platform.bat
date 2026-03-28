@echo off
title Community Conversations Platform
cd /d %~dp0
echo Starting Community Conversations Platform...
echo.
echo Once started, open your browser and go to:
echo    localhost:8501
echo.
echo Password: nhhumanities2025
echo.
python -m streamlit run app.py
pause
