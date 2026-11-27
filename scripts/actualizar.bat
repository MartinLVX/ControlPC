@echo off
rem Descarga la ultima version de ControlPC desde GitHub y reinicia el servidor.
rem Tu config.json (PIN y apps) no se toca.
cd /d "%~dp0..\servidor"
where py >NUL 2>NUL && (py actualizar.py) || (python actualizar.py)
pause
