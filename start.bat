@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在啟動 YT / Bilibili -> GIF Studio...
".venv\Scripts\python.exe" server.py
pause
