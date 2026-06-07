@echo off
setlocal
cd /d "%~dp0"

echo Checking dependencies...
py -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency installation failed.
    pause
    exit /b 1
)

echo Starting bot...
py src\Hi-FiMusicBot.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo Bot exited with error code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
