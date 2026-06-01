@echo off
REM ── Scheduled SolarZero refresh ──────────────────────────
REM Point Windows Task Scheduler at this file (daily, e.g. 6am).
cd /d C:\Manu\ClaudeWork\SolarEnergyProject
call .venv\Scripts\activate.bat 2>nul
python -m src.refresh >> data\refresh.log 2>&1
