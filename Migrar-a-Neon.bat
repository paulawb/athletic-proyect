@echo off
setlocal
title Copia segura de Render a Neon
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\migrate_render_to_neon.ps1"
echo.
echo Si hubo un error, no cambies la conexion de Render y conserva el mensaje.
pause
endlocal
