@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo No encuentro el entorno .venv. Sigue primero los pasos de instalacion del README.txt
  pause
  exit /b 1
)
.venv\Scripts\python.exe main.py
pause
