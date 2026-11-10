---
name: schedule-workflow
description: 자연어 일정 입력 → 파싱 → 충돌 확인 → 캘린더 등록 → 초대 메일 발송까지 순서대로 실행하는 통합 일정 관리 워크플로우
agents:
  - agents/schedule-parser.md
  - agents/conflict-checker.md
  - agents/calendar-register.md
  - agents/invite_sender.md
---

# schedule-workflow — 자연어 기반 자동 일정 관리 워크플로우

## 개요
사용자가 자연어로 일정을 입력하면 4개의 에이전트를 순서대로 실행해
Google Calendar에 일정을 등록하고 참석자에게 초대 메일을 보낸다.
각 단계는 앞 단계가 저장한 JSON 파일을 입력으로 읽는다. 모든 파일은 프로젝트 루트에 UTF-8로 저장하고, 기존 파일은 덮어쓴다.

```
[1] 자연어 입력
     │
[2] schedule-parser ──────▶ parsed_schedule.json
     │
[3] conflict-checker ─────▶ conflict_result.json
     │
[4] calendar-register ────▶ calendar_result.json
     │
[5] invite_sender ────────▶ mail_log.json
     │
[6] 완료 메시지 출력
```

## 공통 기본값
- 언어: 한국어 / 타임존: `Asia/Seoul` / 날짜 해석 기준일: 실행 당일
- 사용자에게 묻는 것은 **1단계 일정 입력**과 **4단계 충돌 시 번호 선택** 두 가지뿐이다. 그 외에는 각 에이전트의 기본값을 적용하고 묻지 않는다.

## 실행 순서

### 1단계 — 자연어 입력 받기
- 워크플로우를 실행할 때 일정 문장이 함께 주어졌으면 그대로 사용한다.
- 없으면 사용자에게 한 번 묻는다:
  `등록할 일정을 자연어로 입력해 주세요. (예: 다음주 화요일 오후 3시에 강남역에서 김민수와 기획 회의)`

### 2단계 — schedule-parser
- 정의: `agents/schedule-parser.md`
- 입력: 1단계 문장
- 출력: `parsed_schedule.json` (날짜, 시작·종료 시간, 제목, 장소, 참석자·이메일, 중요도)
- 날짜나 시간을 해석할 수 없으면 에이전트의 기본값을 적용하고 `assumptions`에 기록한 뒤 계속 진행한다.

### 3단계 — conflict-checker
- 정의: `agents/conflict-checker.md`
- 입력: `parsed_schedule.json`
- 출력: `conflict_result.json`
  - 충돌 없음 → `status: "clear"`
  - 충돌 있음 → `status: "conflict"`, 기존 일정 제목·시간, 같은 날 대안 3개
- 캘린더 조회가 실패하면 한 번 재시도하고, 그래도 실패하면 `status: "error"`로 기록하고 원래 시간으로 4단계를 진행한다.

### 4단계 — calendar-register
- 정의: `agents/calendar-register.md`
- 입력: `conflict_result.json`, `parsed_schedule.json`
- 출력: `calendar_result.json` (이벤트 ID, 캘린더 링크 포함)
- `clear`이면 원래 시간으로 바로 등록한다.
- `conflict`이면 사용자에게 묻는다:
  `기존 일정이 있습니다. 추천시간은 1) {대안1} , 2) {대안2} , 3) {대안3}입니다. 어느 시간으로 등록할까요?(번호입력)`
  - 번호를 입력하지 않거나 잘못 입력하면 **1번 대안을 자동 선택**한다.
- 등록이 실패하면 한 번 재시도하고, 그래도 실패하면 `status: "error"`로 기록하고 5단계로 넘어간다.

### 5단계 — invite_sender
- 정의: `agents/invite_sender.md`
- 입력: `calendar_result.json`, `parsed_schedule.json`
- 출력: `mail_log.json`
- 이메일이 없는 참석자는 Gmail 수발신 내역에서 이름으로 찾는다. 그래도 없으면 건너뛰고 미발송 사유를 기록한다.
- 메일 제목: `[일정초대] {일정제목}` / 본문: 일시, 장소(없으면 '미정'), 구글 캘린더 링크, 회신 요청 문구
- 4단계가 `error`이면 메일을 보내지 않고 전원을 미발송(사유: 캘린더 등록 실패)으로 기록한다.

### 6단계 — 완료 메시지 출력
`calendar_result.json`과 `mail_log.json`을 읽어 아래 형식으로 출력한다.

```
✅ 완료
일정이 등록되었고 참석자에게 메일을 발송하였습니다.
등록된 일정: {제목} ({날짜} {시작시간}~{종료시간}, {장소})
캘린더 링크: {html_link}
발송 메일: {total}건 (성공 {sent} / 미발송 {skipped + failed})
사용한 가정: {각 JSON의 assumptions·notes 요약, 없으면 "없음"}
```

결과에 따라 두 번째 줄을 사실에 맞게 바꾼다.

| 상황 | 두 번째 줄 |
|------|-----------|
| 등록 성공, 1건 이상 발송 | `일정이 등록되었고 참석자에게 메일을 발송하였습니다.` |
| 등록 성공, 발송 0건 | `일정이 등록되었습니다. 이메일을 찾지 못해 메일은 발송하지 않았습니다.` |
| 등록 실패 | `⚠️ 캘린더 등록에 실패하여 메일을 발송하지 않았습니다.` (첫 줄도 `⚠️ 실패`) |

## 산출물
| 단계 | 파일 |
|------|------|
| 2 | `parsed_schedule.json` |
| 3 | `conflict_result.json` |
| 4 | `calendar_result.json` |
| 5 | `mail_log.json` |
