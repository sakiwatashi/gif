@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在啟動 YT -> GIF Studio (http://127.0.0.1:8765)...
start "" http://127.0.0.1:8765
".venv\Scripts\python.exe" server.py
pause
