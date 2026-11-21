@echo off
setlocal
cd /d "%~dp0viewer"

echo.
echo ========================================
echo  policies2BPMN - BPMN Viewer
echo ========================================
echo.

where node >nul 2>&1
if errorlevel 1 (
  echo ERROR: Node.js is not installed or not on PATH.
  echo Install Node.js 18+ from https://nodejs.org/ then try again.
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo Installing npm dependencies - first run...
  call npm install
  if errorlevel 1 (
    echo ERROR: npm install failed.
    pause
    exit /b 1
  )
  echo.
)

echo Starting viewer...
echo Open in browser:  http://localhost:5173
echo.
echo Press Ctrl+C to stop the server.
echo ========================================
echo.

call npm run dev
pause
