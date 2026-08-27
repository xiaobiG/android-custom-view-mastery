@echo off
setlocal
cd /d "%~dp0"
call npm ci || exit /b 1
call npm run check || exit /b 1
call npm run build || exit /b 1
echo.
echo VitePress build complete: %CD%\dist
echo For stable local reading, run read.cmd.
