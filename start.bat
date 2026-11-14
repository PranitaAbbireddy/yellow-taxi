@echo off
set "NODE_EXE=%LOCALAPPDATA%\Programs\cursor\resources\app\resources\helpers\node.exe"
if exist "%NODE_EXE%" (
    echo Starting NYC Taxi Demand App using %NODE_EXE%...
    "%NODE_EXE%" app/server.js
) else (
    where node >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        echo Starting NYC Taxi Demand App using system node...
        node app/server.js
    ) else (
        echo Error: Node.js was not found on this system.
        pause
    )
)
