@echo off
REM Create virtual environment
python -m venv .venv

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Upgrade pip (optional but recommended)
python -m pip install --upgrade pip

REM Install dependencies
pip install -r requirements.txt

REM Run the script
python script.py

REM Keep the window open
pause
