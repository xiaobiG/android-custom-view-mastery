@echo off
setlocal
cd /d "%~dp0"
call npm ci || exit /b 1
echo.
echo Open this address after the server is ready:
echo http://localhost:4000/
echo Do not open _book\index.html directly; file:// can block HonKit navigation.
echo.
call npm run serve
