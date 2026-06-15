@echo off
setlocal
color D0

cd /d "%~dp0"

:: Cek apakah 'py' launcher tersedia (default di Windows)
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

%PYTHON_CMD% touch_panel\touch_panel_app.py --launch --windowed
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Aplikasi berhenti dengan error.
    pause
)
exit /b %errorlevel%
