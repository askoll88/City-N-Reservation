@echo off
chcp 65001 >nul
title STALKER Bot - Start

echo ========================================
echo     STALKER VK Bot - Starter
echo ========================================
echo.

cd /d "%~dp0..\.."

echo Starting bot...
start "" cmd /c "py main.py"

echo Bot started!
echo ========================================
timeout /t 1 /nobreak >nul
