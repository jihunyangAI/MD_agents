@echo off
chcp 65001 > nul
setlocal

rem ============================================================
rem  긴급 파일 전송 - 1회 확인 (작업 스케줄러 5분 주기 실행용)
rem  1) 새 텔레그램 메시지가 있는지 Python으로 먼저 확인 (Claude 비용 없음)
rem  2) 있을 때만 Claude Code로 /file-transfer 절차 실행 후 종료
rem  ※ 이전 실행이 진행 중이면 작업 스케줄러가 새 실행을 건너뜀 (기본 설정)
rem  ※ run_listener.bat 과 동시에 쓰지 말 것 (같은 메시지를 두 번 처리할 수 있음)
rem ============================================================

cd /d "%~dp0"
set PYTHONUTF8=1
rem 저장된 장기 토큰(setx CLAUDE_CODE_OAUTH_TOKEN)을 바로 읽어 옴 - 로그아웃 없이 적용
for /f "skip=2 tokens=2,*" %%a in ('reg query HKCU\Environment /v CLAUDE_CODE_OAUTH_TOKEN 2^>nul') do set "CLAUDE_CODE_OAUTH_TOKEN=%%b"
if not exist logs mkdir logs

python -X utf8 -I scripts\telegram_poll.py --peek > nul 2>&1
if errorlevel 3 exit /b 0
if errorlevel 1 (
  echo [%date% %time:~0,8%] 텔레그램 확인 실패 >> logs\scheduler.log
  exit /b 1
)

echo [%date% %time:~0,8%] 새 메시지 처리 시작 >> logs\scheduler.log
claude -p "commands/file-transfer.md 파일을 읽고 그 절차를 그대로 수행해. $ARGUMENTS 는 비어 있다. 이 프로젝트의 agents/, commands/, scripts/ 외의 작업은 하지 마." ^
  --model sonnet ^
  --permission-mode default ^
  --allowedTools "Read" "Bash(cd:*)" "Bash(python -X utf8 -I scripts/telegram_poll.py:*)" "Bash(python -X utf8 -I scripts/telegram_reply.py:*)" "Bash(python -X utf8 -I scripts/file_finder.py:*)" "Bash(python -X utf8 -I scripts/mail_sender.py:*)" >> logs\scheduler.log 2>&1
echo [%date% %time:~0,8%] 처리 종료 (코드 %errorlevel%) >> logs\scheduler.log
exit /b 0
