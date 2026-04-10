@echo off
chcp 65001 >nul
title STALKER Bot - Stop

echo ========================================
echo     STALKER VK Bot - Stopper
echo ========================================
echo.

echo [INFO] Stopping bot processes...

REM Останавливаем все процессы py с main.py
for /f "tokens=2" %%a in ('wmic process where "name='py.exe'" get processid^,commandline 2^>nul ^| findstr "main.py"') do (
    echo [STOP] Killing process %%a
    taskkill /F /PID %%a >nul 2>&1
)

REM Также ищем по порту если бот использует сервер
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo [STOP] Killing process on port 8000: %%a
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [DONE] Bot stopped!
echo ========================================
