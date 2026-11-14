@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv
  if errorlevel 1 goto blad
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto blad
.venv\Scripts\python.exe dzialki.py
if errorlevel 1 goto blad
exit /b 0
:blad
 echo Nie udalo sie uruchomic programu. Sprawdz komunikat powyzej i instalacje Python 3.10+.
 pause
 exit /b 1
