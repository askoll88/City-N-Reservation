@echo off
chcp 65001 >nul
title Stop Bot

echo ========================================
echo   CITY N: FORBIDDEN ZONE
echo   Stopping game bot...
echo ========================================
echo.

tasklist /fi "imagename eq python.exe" /fo csv 2>nul | findstr /i "python.exe" >nul
if %errorlevel%==0 (
    echo Python process found. Stopping...
    taskkill /f /im python.exe
    echo Bot stopped.
) else (
    echo Bot is not running.
)

echo.
echo ========================================
echo   Done. Press any key...
echo ========================================
pause >nul
