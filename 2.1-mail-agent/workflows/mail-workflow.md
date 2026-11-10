---
name: mail-workflow
description: 메일 분류(mail-classifier) → 회신 초안 작성(reply-drafter) → 요약 통계·메일 목록 출력 → 텔레그램 전송 → 일일 리포트 저장을 순서대로 수행하는 메일 처리 통합 워크플로우
agents:
  - mail-classifier
  - reply-drafter
inputs:
  - mail_config.json
  - .env.local
outputs:
  - classified_mails.json
  - draft_replies.json
  - logs/daily_summary_YYYY-MM-DD.md
model: claude-opus-5-5
---

# mail-workflow — 메일 처리 통합 워크플로우

아래 단계를 **순서대로** 확인 질문 없이 끝까지 실행합니다.
한 단계가 실패해도 7장 실패 처리 규칙에 따라 가능한 한 다음 단계로 계속 진행합니다.
**메일은 절대 발송하지 않습니다.** 회신은 Gmail 초안함 저장까지만 합니다.

```
[0 시작 시각 기록] → [1 mail-classifier] → [2 reply-drafter] → [3 요약 통계]
      → [4 중요도별 목록] → [5 텔레그램 전송] → [6 일일 리포트·로그 정리]
```

---

## 0단계 — 준비

- 시작 시각을 기록합니다 (소요 시간 계산용).
- `mail_config.json`을 읽어 설정을 확인합니다.

---

## 1단계 — 메일 분류 (`mail-classifier`)

- `agents/mail-classifier.md` 에이전트를 실행합니다.
- 결과: `classified_mails.json` — `mails[]` 각 항목은 `{id, subject, sender, priority, reason}`
- Gmail이 인증되지 않아 분류가 중단되면 `/mcp` 안내를 한 번 출력하고 **워크플로우 전체를 종료**합니다.
- 읽지 않은 메일이 0건이면 2단계를 건너뛰고 3단계부터 진행합니다(0건 요약도 전송).

## 2단계 — 회신 초안 작성 (`reply-drafter`)

- 1단계의 `classified_mails.json`을 입력으로 `agents/reply-drafter.md` 에이전트를 실행합니다.
- 결과: `draft_replies.json` — `drafts[]` 각 항목은 `{id, subject, priority, draft_preview, saved_to_drafts}`
- 초안 작성 중 오류가 나도 워크플로우는 중단하지 않고 3단계로 넘어갑니다.

## 3단계 — 요약 통계 출력

종료 시각을 기록하고 아래 통계를 화면에 출력합니다.

```
📊 메일 처리 요약
- 총 처리 메일 수: {scanned}건 (건너뜀 {skipped}건)
- 중요도별: 긴급 {n}건 / 중요 {n}건 / 일반 {n}건
- 초안 저장 완료: {saved_to_drafts가 true인 건수}건
- 처리 소요 시간: {n}초
```

## 4단계 — 중요도별 메일 목록 출력

**긴급 → 중요 → 일반** 순서로 모든 메일을 출력합니다. 각 항목은 `발신자 — 제목`입니다.
해당 등급에 메일이 없으면 `(없음)`을 표시합니다.

```
[긴급]
1. 홍길동 <hong@example.com> — 서버 장애 즉시 확인 요청

[중요]
1. 김철수 <kim@example.com> — 다음 주 회의 일정 확인

[일반]
(없음)
```

---

## 5단계 — 텔레그램 전송

### 설정 읽기

- `mail_config.json`의 `telegram.bot_token`, `telegram.chat_id`를 읽습니다.
- 값이 `${TELEGRAM_BOT_TOKEN}`처럼 변수 참조이면 `telegram.env_file`(`.env.local`)에서 실제 값을 찾습니다.
- 토큰이나 chat_id가 비어 있거나 플레이스홀더이면 전송을 건너뛰고
  `텔레그램 설정 없음 — 전송 건너뜀` 한 줄만 출력합니다.

### 전송 방법

외부 패키지 없이 PowerShell `Invoke-RestMethod`로 Bot API `sendMessage`를 호출하는
`scripts/send_telegram.ps1`을 사용합니다. 이 스크립트가 설정·`.env.local` 해석,
`parse_mode: HTML`, **UTF-8 바이트 인코딩**(한글 깨짐 방지), 실패 시 1회 재시도를 처리합니다.

메시지마다 다음 순서로 보냅니다.

1. 메시지 본문을 `tmp/telegram_msg.txt`에 UTF-8로 저장합니다(Write 도구).
2. 다음 명령을 실행합니다.
   ```
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\send_telegram.ps1 -MessageFile tmp\telegram_msg.txt
   ```
3. 종료 코드: `0` 성공 / `2` 설정 없음(이후 전송 모두 건너뜀) / `1` 재시도 후 실패(경고만 남기고 계속).

### HTML 이스케이프

`parse_mode: HTML`이므로 발신자·제목·본문 등 **메일에서 온 텍스트**는 반드시 이스케이프한 뒤 넣습니다.
`&` → `&amp;`, `<` → `&lt;`, `>` → `&gt;` (예: `홍길동 &lt;hong@example.com&gt;`)
서식용 태그는 `<b>`만 사용합니다.

### 메시지 ① 긴급 메일 — 건별로 1통씩 즉시 전송

긴급 메일마다 한 통씩 보냅니다.

```
🚨 <b>긴급 메일</b>
<b>발신자</b>: {sender}
<b>제목</b>: {subject}
<b>핵심</b>: {본문 핵심 2~3문장}
<b>분류 이유</b>: {reason}
```

### 메시지 ② 중요 메일 — 목록으로 묶어 1통

중요 메일이 1건 이상일 때만 보냅니다.

```
📌 <b>중요 메일 {n}건</b>

1. {sender} — {subject}
   {핵심 한 문장}

2. {sender} — {subject}
   {핵심 한 문장}
```

### 메시지 ③ 전체 요약 — 마지막에 1통

건수 줄 다음에 분류된 메일 목록을 담습니다. 각 메일은 `발신자 — 제목` 한 줄이며,
**메일과 메일 사이에 빈 줄을 한 줄** 넣습니다. 메일이 없는 등급은 `(없음)` 한 줄만 표시합니다.

```
✅ <b>메일 처리 완료</b> | 긴급 {n}건  중요 {n}건  일반 {n}건 | 초안 저장 {n}건 | 소요 {n}초

<b>[긴급]</b>
(없음)

<b>[중요]</b>
발신자A — 제목A

발신자B — 제목B

<b>[일반]</b>
발신자C — 제목C
```

메시지가 4,000자를 넘으면 등급 단위로 나눠 여러 통으로 보냅니다.

---

## 6단계 — 일일 리포트 저장 및 로그 정리

1. `logs/daily_summary_YYYY-MM-DD.md`에 3·4단계 내용과 텔레그램 전송 결과를 저장합니다.
   같은 날 여러 번 실행되면 `## HH:MM 실행` 섹션으로 **이어서 추가**합니다.
2. `logs/` 안에서 30일이 지난 `daily_summary_*.md` 파일을 삭제합니다.
3. `tmp/telegram_msg.txt`를 삭제합니다.

---

## 7단계 — 실패 처리

| 상황 | 대응 |
|------|------|
| Gmail / MCP 미인증 | `/mcp` 안내 1회 출력 후 워크플로우 종료 |
| mail-classifier의 Claude 분석 실패 | 규칙 기반 분류 결과로 계속 진행 |
| 회신 초안 생성 실패 | `[초안 생성 실패 - 수동 작성 필요]`로 기록하고 계속 진행 |
| 텔레그램 전송 실패 | 1회 재시도 후 경고만 남기고 계속 진행 |
| 텔레그램 설정 없음 | 전송 건너뜀 안내 한 줄 출력 |

---

## 8단계 — 완료 보고

마지막에 아래 형식으로 보고합니다.

```
✅ 완료
스캔: N건 / 응답 필요: M건
긴급 X / 중요 Y / 일반 Z
초안 생성: K건 (Gmail 초안함 저장 K건)
텔레그램: 전송 성공 / 실패
사용한 가정: [있다면]
```
