@echo off
setlocal
cd /d "%~dp0"
call npm ci || exit /b 1
call npm run check || exit /b 1
call npm run build || exit /b 1
echo.
echo Build complete: %CD%\_book
echo For clickable local reading, run serve.cmd and open http://localhost:4000/
