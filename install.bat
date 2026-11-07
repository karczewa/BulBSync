@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
echo.
echo Opcjonalnie: szybsze przechwytywanie ekranu (DXGI). Jesli sie nie zainstaluje, aplikacja i tak dziala.
python -m pip install dxcam
pause
