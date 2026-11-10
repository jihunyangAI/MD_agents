# MD_agents

Claude Code로 만든 **Markdown 기반 에이전트·워크플로우** 실습 모음입니다.
각 실습 폴더의 `CLAUDE.md`가 작업 지침서 역할을 하며, 에이전트(`agents/*.md`)와 워크플로우(`workflows/*.md`)는
YAML 프런트매터 + 본문 형식의 Markdown 파일로 정의되어 있습니다.

## 실습 목록

| 폴더 | 내용 | 주요 산출물 |
|------|------|-------------|
| [`1.1-family-travel-planner`](1.1-family-travel-planner) | 가족 여행 정보(여행지·기간·예산·구성)를 입력하면 일자별 코스, 숙소 추천, 예산 검증, 최종 여행 계획서를 생성 | `family-travel-workflow.json`, `travel_plan.md`, `budget_summary.json` |
| [`1.2-schedule-assistant`](1.2-schedule-assistant) | 자연어 일정 텍스트를 파싱해 캘린더 충돌을 확인하고 Google Calendar 등록·초대 메일까지 처리 | `agents/schedule-parser.md` 외 3개, `workflows/schedule-workflow.md` |
| [`2.1-mail-agent`](2.1-mail-agent) | Gmail 미열람 메일을 긴급/중요/일반으로 분류하고 회신 초안을 Gmail 초안함에 저장, 결과를 텔레그램으로 알림 | `agents/mail-classifier.md`, `agents/reply-drafter.md`, `workflows/mail-workflow.md` |

## 2.1 mail-agent 구조

```
mail_config.json ─┐
.env.local ───────┤   (텔레그램 토큰·chat_id — 저장소에 포함되지 않음)
                  ▼
[mail-classifier] → classified_mails.json
        │              (키워드·발신자 규칙 + Claude 문맥 분석, 신뢰도 높은 쪽 채택)
        ▼
[reply-drafter]   → draft_replies.json + Gmail 초안함
        │              (긴급=격식체 / 중요=정중체 / 일반=간략체, 발송은 하지 않음)
        ▼
[mail-workflow]   → 요약 통계 · 중요도별 목록 · 텔레그램 전송 · logs/daily_summary_YYYY-MM-DD.md
```

- 분류·초안 모델: Claude (`claude-opus-5-5`)
- 텔레그램 전송: `scripts/send_telegram.ps1` (PowerShell `Invoke-RestMethod`, HTML·UTF-8, 실패 시 1회 재시도, `-DryRun` 지원)
- 회신 메일은 **절대 자동 발송하지 않으며** 초안 저장까지만 수행합니다.

### 실행 준비

1. Claude Code에서 Gmail 커넥터를 연결합니다 (`/mcp`).
2. `2.1-mail-agent/.env.local`을 만듭니다.
   ```
   TELEGRAM_BOT_TOKEN=<BotFather에서 받은 토큰>
   TELEGRAM_CHAT_ID=<내 chat_id>
   ```
3. `mail_config.json`에서 `important_senders`, `urgent_keywords`, `check_interval` 등을 조정합니다.
4. Claude Code에서 `workflows/mail-workflow.md 워크플로우를 실행해줘`라고 요청합니다.

텔레그램 설정만 먼저 확인하려면:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\send_telegram.ps1 -MessageFile tmp\msg.txt -DryRun
```

## 보안 메모

- `.env`, `.env.*` 파일은 `.gitignore`로 제외됩니다. 토큰·키는 커밋하지 마세요.
- `classified_mails.json`, `draft_replies.json`, `logs/`는 실행 결과물로, 실행한 계정의 메일 제목·발신자가 담깁니다.
