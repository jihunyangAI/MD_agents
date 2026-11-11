@echo off
REM ============================================================
REM  news-monitor daily briefing - runs every day at 08:00
REM  Step 1-3 (news, impact analysis, jobs): Claude Code headless (-p)
REM  Step 4 (Telegram send): python newsletter_sender.py
REM  Usage: run_schedule.bat          (full run)
REM         run_schedule.bat --check  (show settings only, no run)
REM ============================================================
setlocal
cd /d "%~dp0"

set "CLAUDE=%USERPROFILE%\.local\bin\claude.exe"
set "PYTHON=C:\Python314\python.exe"
set "PYTHONIOENCODING=utf-8"
set "TOOLS=Read,Write,Edit,Glob,Grep,Bash(python:*),Bash(cp:*),Bash(mkdir:*),Bash(ls:*),mcp__tavily__tavily_search,mcp__tavily__tavily_extract"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%i"
if not exist logs mkdir logs
set "LOG=logs\schedule_%TODAY%.log"

if /i "%~1"=="--check" goto :check

echo ===== [%date% %time%] daily briefing start ===== >> "%LOG%"

REM ---- Step 1-3 + upcoming events (no sending) ----
"%CLAUDE%" -p --allowedTools "%TOOLS%" < schedule_prompt.txt >> "%LOG%" 2>&1
if errorlevel 1 echo [WARN] collect/analyze step failed - sending with existing data >> "%LOG%"

REM ---- Step 4 Telegram send (script retries once after 3 min on failure) ----
"%PYTHON%" newsletter_sender.py >> "%LOG%" 2>&1
set "SEND_RESULT=%errorlevel%"

echo ===== [%date% %time%] end (send exit %SEND_RESULT%) ===== >> "%LOG%"

REM ---- delete schedule logs older than 30 days ----
forfiles /p logs /m schedule_*.log /d -30 /c "cmd /c del @path" >nul 2>&1

endlocal & exit /b %SEND_RESULT%

:check
echo DIR    = %cd%
echo TODAY  = %TODAY%
echo LOG    = %LOG%
if exist "%CLAUDE%" (echo CLAUDE = OK %CLAUDE%) else (echo CLAUDE = NOT FOUND %CLAUDE%)
if exist "%PYTHON%" (echo PYTHON = OK %PYTHON%) else (echo PYTHON = NOT FOUND %PYTHON%)
if exist schedule_prompt.txt (echo PROMPT = OK) else (echo PROMPT = NOT FOUND)
if exist newsletter_sender.py (echo SENDER = OK) else (echo SENDER = NOT FOUND)
endlocal & exit /b 0
