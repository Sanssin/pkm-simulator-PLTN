@echo off
REM PLTN Video Display - Development Mode
REM Updated with 17-button keyboard controls

echo ==========================================
echo PLTN Video Display - Development Mode
echo ==========================================
echo.

REM Check pygame atau pygame-ce
py -c "import pygame" 2>nul
if errorlevel 1 (
    echo [ERROR] pygame / pygame-ce not installed
    echo    Install: pip install pygame-ce
    pause
    exit /b 1
) else (
    echo [OK] pygame installed
)

echo.
echo Starting development mode (windowed, test mode)...
echo.
echo ==========================================
echo KEYBOARD CONTROLS (17 Buttons)
echo ==========================================
echo.
echo === PUMP CONTROLS ===
echo   1/2 = Primary ON/OFF
echo   4/5 = Secondary ON/OFF
echo   7/8 = Tertiary ON/OFF
echo.
echo === CONTROL RODS (Hold for continuous) ===
echo   Q/W = Safety UP/DOWN
echo   E/R = Shim UP/DOWN
echo   T/Y = Regulating UP/DOWN
echo.
echo === PRESSURE ===
echo   Arrow UP/DOWN = Pressure UP/DOWN
echo.
echo === SYSTEM CONTROLS ===
echo   F1 = Start Auto Simulation
echo   F2 = Reactor Reset
echo   F3 = Emergency Shutdown
echo.
echo === EXIT ===
echo   ESC = Exit application
echo.
echo ==========================================
echo.
echo Press any key to start...
pause >nul

py video_display_app.py --test --windowed
