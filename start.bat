@echo off
title AI Fraud Detection System
color 0A

echo ============================================================
echo   AI Fraud Detection System
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

:: Install dependencies
echo [1/3] Installing Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo        Done.

:: Setup DB + train models
echo [2/3] Setting up database and training ML models...
python setup_db.py
if errorlevel 1 (
    echo [ERROR] Setup failed. Check MySQL connection and .env settings.
    pause
    exit /b 1
)

:: Start server
echo [3/3] Starting Flask server...
echo.
echo ============================================================
echo   Open browser:   http://localhost:5000
echo   Login:          admin / admin123
echo   Stop server:    Ctrl+C
echo ============================================================
echo.
python run.py

pause
