@echo off
setlocal
cd /d "%~dp0"

echo.
echo ========================================
echo  policies2BPMN - Regenerate artifacts
echo ========================================
echo.
echo Parses policies\blackrockPTIP.html and writes
echo JSON / BPMN into outputs\
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python is not installed or not on PATH.
  echo Install Python 3.10+ and try again.
  pause
  exit /b 1
)

echo Ensuring Python packages (beautifulsoup4, lxml)...
python -m pip install -q beautifulsoup4 lxml
if errorlevel 1 (
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

echo.
echo Running converter...
python scripts\one_off_convert.py
if errorlevel 1 (
  echo ERROR: conversion failed.
  pause
  exit /b 1
)

echo.
echo Done. Artifacts are in outputs\
echo Restart or refresh the viewer to load updates.
echo ========================================
pause
