@echo off
title Jimmy Jensen - TeamSpeak AI Voice Bot
cd /d "%~dp0"
echo ===================================================
echo   Starting Jimmy Jensen TeamSpeak Voice Bot...
echo ===================================================

:: Ensure virtual environment python is used
.venv\Scripts\python.exe -u autonomous_bot.py
pause
