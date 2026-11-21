@echo off
cd /d "%~dp0"

REM Zip offline demo (main + role views). Rebuilds when Python is available.

set "ROOT=%~dp0"
set "ZIP_OUT=%ROOT%notebooks\offline_p2b_OFFLINE_DEMO.zip"
set "PACK=%ROOT%notebooks\offline_p2b"
set "BUILD=%ROOT%notebooks\build_offline_p2b.py"

where python >nul 2>&1
if errorlevel 1 goto ZIP_EXISTING

echo Building offline pack then zipping...
python "%BUILD%" --zip-path "%ZIP_OUT%"
if not errorlevel 1 goto DONE

echo Build failed - zipping existing pack only...
python "%BUILD%" --zip-only --zip-path "%ZIP_OUT%"
if not errorlevel 1 goto DONE

:ZIP_EXISTING
if not exist "%PACK%\index.html" (
  echo ERROR: Missing %PACK%\index.html
  echo Run notebooks\00_RUN_ONE_POLICY.ipynb through section 3b first.
  exit /b 1
)
echo Zipping existing pack with PowerShell...
powershell -NoProfile -Command "if (Test-Path -LiteralPath $env:ZIP_OUT) { Remove-Item -LiteralPath $env:ZIP_OUT -Force }; Compress-Archive -Path (Join-Path $env:PACK '*') -DestinationPath $env:ZIP_OUT -Force"
if errorlevel 1 (
  echo ERROR: Zip failed.
  exit /b 1
)

:DONE
echo.
echo Offline demo zip:
echo   %ZIP_OUT%
echo.
echo Unzip, then open offline_p2b\index.html
echo Role views open from the Intelligence lens on the main page.
exit /b 0
