@echo off
setlocal

cd /d "%~dp0"

REM Cari Python executable (py launcher, python, atau python3)
where py >nul 2>&1
if not errorlevel 1 (
    set PYTHON=py
    goto :run
)

where python >nul 2>&1
if not errorlevel 1 (
    set PYTHON=python
    goto :run
)

where python3 >nul 2>&1
if not errorlevel 1 (
    set PYTHON=python3
    goto :run
)

echo [ERROR] Python tidak ditemukan. Pastikan Python sudah terinstall dan ada di PATH.
pause
exit /b 1

:run
%PYTHON% touch_panel\touch_panel_app.py --launch --windowed
if %errorlevel% neq 0 (
    echo [ERROR] Terjadi masalah saat menjalankan aplikasi!
    pause
)
exit /b %errorlevel%
