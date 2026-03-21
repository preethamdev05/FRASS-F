@echo off
REM Face Recognition Attendance System — Windows Launcher (Auto-Restart)
REM Usage: run.bat

:loop
echo ==========================================
echo   Face Recognition Attendance System
echo ==========================================

REM Create venv if needed
if not exist "venv" (
    echo [1/3] Creating virtual environment...
    python -m venv venv
)

REM Install dependencies if needed
if not exist "venv\.installed" (
    echo [2/3] Installing dependencies (first run, ~2 min)...
    call venv\Scripts\pip install --upgrade pip -q
    call venv\Scripts\pip install insightface onnxruntime opencv-python-headless flask numpy Pillow -q
    echo. > venv\.installed
    echo       Dependencies installed
) else (
    echo [2/3] Dependencies ready
)

REM Init database
echo [3/3] Initializing database...
call venv\Scripts\python models.py

echo.
echo ==========================================
echo   Server running!
echo   Open: http://localhost:5000
echo   Press Ctrl+C to stop
echo ==========================================
echo.

call venv\Scripts\python app.py

echo.
echo Server stopped. Restarting in 3 seconds...
timeout /t 3 >nul
goto loop
