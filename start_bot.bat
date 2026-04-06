@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONLOGLEVEL=INFO
title City N: Forbidden Zone - Bot

echo ========================================
echo   CITY N: FORBIDDEN ZONE
echo   Starting game bot...
echo ========================================
echo.

py -X utf8 main.py
set EXITCODE=%errorlevel%

echo.
echo ========================================
echo   Bot exited with code: %EXITCODE%
echo   Press any key to close...
echo ========================================
pause >nul
