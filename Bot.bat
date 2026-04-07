@echo off
title ZeusX Relister Bot
color 0a

:: Pastikan script membaca file python dari folder tempat Bot.bat ini berada
cd /d "%~dp0"

echo =========================================
echo.
echo    STARTING ZEUSX AUTO-RELISTER BOT...
echo.
echo =========================================
echo.

:: Tunggu 2 detik biarkan server menyala dulu, lalu buka browser
start "" "http://localhost:8000"

:: Jalankan python server
python server.py

echo.
echo Server telah berhenti.
pause
