@echo off
chcp 65001 >nul
title STALKER Bot - Restart

echo ========================================
echo     STALKER VK Bot - Restart
echo ========================================
echo.

echo [STEP 1] Stopping bot....
call "%~dp0stop_bot.bat"

echo.
echo [STEP 2] Waiting 3 seconds....
timeout /t 3 /nobreak >nul

echo.
echo [STEP 3] Starting bot...
call "%~dp0start_bot.bat"

echo.
echo [DONE] Bot restarted!
echo ========================================
