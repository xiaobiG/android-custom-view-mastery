@echo off
setlocal
cd /d "%~dp0"
call npm ci || exit /b 1
echo.
echo VitePress development server:
echo http://127.0.0.1:4000/
echo.
call npm run serve -- --port 4000
