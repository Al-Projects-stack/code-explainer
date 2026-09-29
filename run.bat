@echo off
REM Code Explainer launcher — double-click to start the Web UI.
REM Keep this window open while you use the app in your browser.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
  python code_explainer.py --web
) else (
  py code_explainer.py --web
)
if %errorlevel% neq 0 (
  echo.
  echo [ERROR] Could not start. Is Python installed? Try: py -3 code_explainer.py --web
)
pause
