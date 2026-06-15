@echo off
setlocal

cd /d "%~dp0"
py touch_panel\touch_panel_app.py --launch --windowed
exit /b %errorlevel%
