@echo off
rem Inicia ControlPC en una ventana, mostrando la direccion y el PIN.
cd /d "%~dp0..\servidor"
where py >nul 2>nul && (py servidor.py) || (python servidor.py)
pause
