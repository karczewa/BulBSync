@echo off
cd /d "%~dp0"
python -m bulbsync
if errorlevel 1 pause
