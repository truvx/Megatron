@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-Megatron.ps1" %*
set "MEGATRON_EXIT=%ERRORLEVEL%"
echo.
echo Megatron installer exited with status %MEGATRON_EXIT%.
pause
exit /b %MEGATRON_EXIT%
