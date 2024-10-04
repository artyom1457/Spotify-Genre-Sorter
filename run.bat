@echo off

REM Check if the virtual environment exists
if not exist ".\venv\Scripts\python.exe" (
    echo Virtual environment not found! Please create it first.
    exit /b
)

REM Activate the virtual environment and run the main.py script
echo Starting the Flask application...
start "" ".\venv\Scripts\python.exe" .\main.py

REM Wait for a few seconds to ensure the server is up and running
timeout /t 5 /nobreak >nul

REM Open the default web browser with the localhost link
start http://localhost:5000

exit
