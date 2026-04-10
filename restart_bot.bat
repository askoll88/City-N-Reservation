@echo off
chcp 65001 >nul
title STALKER Bot - Restart

echo ========================================
echo     STALKER VK Bot - Restart
echo ========================================
echo.

echo [STEP 1] Stopping bot....
call stop_bot.bat

echo.
echo [STEP 2] Waiting 3 seconds....
timeout /t 3 /nobreak >nul

echo.
echo [STEP 3] Starting bot...
call start_bot.bat

echo.
echo [DONE] Bot restarted!
echo ========================================
