@echo off
title TopWinLose BNB - Top Winner / Loser Binance Futures
set "DIR=%USERPROFILE%\TopWinLose"
set "RAW=https://raw.githubusercontent.com/meohocgioi/topwinlosebnb/main/topwinlose.py"
if not exist "%DIR%" mkdir "%DIR%"
cd /d "%DIR%"

python --version >nul 2>&1
if errorlevel 1 (
  echo Chua co Python - dang thu cai tu dong...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo Neu cai xong: DONG cua so nay va bam dup TopWinLose.bat lan nua.
  echo Neu cai loi: tai Python tai https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) roi chay lai.
  pause
  exit /b
)

if not exist topwinlose.py (
  echo Dang tai tool lan dau...
  curl -L -s -o topwinlose.py "%RAW%"
  if not exist topwinlose.py (
    echo Khong tai duoc tool. Kiem tra mang roi chay lai.
    pause
    exit /b
  )
)

echo Dang kiem tra thu vien...
python -m pip install -q --disable-pip-version-check aiohttp
set TWL_LAUNCHER=1
:loop
python topwinlose.py
if %errorlevel%==42 (
  set TWL_RESTARTED=1
  goto loop
)
echo.
echo Tool da dung. Bam phim bat ky de dong cua so.
pause >nul
