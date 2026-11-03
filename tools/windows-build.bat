@echo off
REM windows-build.bat — Produce a standalone openline.exe (no Python needed to run)
REM
REM Run this ONCE on a Windows machine that has Python installed, then upload the
REM resulting dist\openline.exe to your GitHub Release so install.ps1 can fetch it.
REM
REM Requirements on the BUILD machine only: Python 3.8+ and internet access.

setlocal
cd /d "%~dp0\.."

echo === Building openline.exe ===

REM Make sure the embedded files are injected first.
python tools\build_openline.py || goto :err

REM Install PyInstaller into an isolated venv so we don't touch system Python.
python -m venv .build-venv || goto :err
call .build-venv\Scripts\activate.bat || goto :err
python -m pip install --upgrade pip >nul
python -m pip install pyinstaller || goto :err

REM openline.py is fully self-contained (files embedded as base64), so a plain
REM one-file build needs no --add-data.
pyinstaller --onefile --console --name openline openline.py || goto :err

echo.
echo Done. Standalone binary: dist\openline.exe
echo Upload that to your GitHub Release (tag "latest") for install.ps1.
goto :eof

:err
echo.
echo BUILD FAILED. See the output above.
exit /b 1
