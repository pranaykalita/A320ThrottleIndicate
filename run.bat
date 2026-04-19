@echo off
title A32NX Throttle Overlay
cd /d "%~dp0"

echo ================================================
echo   A32NX Throttle Overlay
echo ================================================
echo.
echo  !! START MICROSOFT FLIGHT SIMULATOR FIRST !!
echo     Load into a flight, THEN press any key.
echo.
pause

:: Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)

:: Install deps if missing
python -c "import SimConnect" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing SimConnect...
    python -m pip install -r requirements.txt
)


echo.
echo [START] Launching overlay...
echo         Console will show live throttle data.
echo         Right-click overlay to open Settings.
echo         Click X on overlay to quit.
echo.
python Thrt_indic.py
pause