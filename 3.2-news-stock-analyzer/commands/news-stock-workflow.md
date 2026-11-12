---
description: 뉴스 기반 주식 영향 분석 워크플로 — 뉴스 수집 → 영향 분석 → 리포트 출력 → 텔레그램 발송을 한 번에 실행
argument-hint: (인자 없음)
allowed-tools: Read, Write, Edit, Bash, WebSearch, mcp__tavily__tavily_search, mcp__tavily__tavily_extract
---

# news-stock-workflow — 뉴스 기반 주식 영향 분석 통합 워크플로

오늘의 핫이슈 뉴스 TOP 5를 수집하고, 종목·섹터 영향을 분석해 리포트로 출력한 뒤 텔레그램으로 발송한다.
**확인 질문 없이 끝까지 진행**하고, 마지막에 완료 메시지를 출력한다.

## 실행 트리거 (둘 다 동일 동작)
| 방법 | 입력 |
|------|------|
| 슬래시 명령어 | `/news-stock-workflow` |
| 자연어 | `지금 뉴스 분석해줘` |

## 전체 흐름 (반드시 순차 실행 — 각 단계는 직전 산출물에 의존)
```
① news-collector   (웹검색)                 ──▶ today_news.json
        │
② impact-analyzer  (경제적 인과관계 분석)     ──▶ impact_analysis.json
        │
③ report-printer   (python report_printer.py) ──▶ daily_report.md + 콘솔 출력 + logs/report_YYYY-MM-DD.md
        │
④ telegram-sender  (python telegram_sender.py) ──▶ 텔레그램 발송 + logs/telegram_YYYY-MM-DD.log
        │
⑤ 완료 메시지 출력 + daily_report.md 자동 오픈
```

---

## ① news-collector — 오늘의 핫이슈 뉴스 수집
- `agents/news-collector.md`를 읽고 그 지침대로 실행한다.
- 웹검색 도구(tavily_search, WebSearch)로 오늘 날짜 기준 TOP 5를 수집한다. 해외(Reuters·Bloomberg·NBC·FT·WSJ)를 우선하고, 국내(연합뉴스·한국경제)는 보조로 쓴다.
- 검색은 기준별(지정학·경제정책·산업·기업)로 **병렬** 실행해도 된다.
- 결과를 `today_news.json`에 덮어쓴다.
- **검증**: JSON 파싱이 되고 `news` 배열이 1건 이상이어야 한다. 0건이면 워크플로를 중단하고 사유를 보고한다(5건 미만이면 수집된 수만큼 진행).

## ② impact-analyzer — 주식 영향 분석
- `agents/impact-analyzer.md`를 읽고, ①의 `today_news.json`을 입력으로 분석한다.
- 뉴스별로 강세/약세 종목·섹터(대표 3종목, 국내 우선), 이유, 영향 강도(높음/보통/낮음), `overall`(🔺/🔻/➖)을 채운다.
- `summary`(강세/약세/중립 개수)와 `market_summary`(오늘의 한줄요약)를 반드시 채운다.
- 결과를 `impact_analysis.json`에 덮어쓴다.
- **검증**: `summary`의 개수가 `analysis[].overall` 집계와 일치하는지 확인한다.

## ③ report-printer — 리포트 출력·저장
```
python report_printer.py
```
- 터미널에 리포트를 출력하고 `daily_report.md`를 저장한다(`logs/report_YYYY-MM-DD.md` 백업, 60일 보관).
- 출력된 리포트 전문을 사용자에게 그대로 보여준다.

## ④ telegram-sender — 텔레그램 발송
```
python telegram_sender.py
```
- `.env`의 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 사용하고 `requests`로 발송한다.
- 콘솔에 **발송 결과(성공/실패)와 메시지 길이**를 출력한다.
- 실패하면 스크립트가 1회 재시도하고, 결과를 `logs/telegram_YYYY-MM-DD.log`에 기록한다.
- **실패해도 전체를 중단하지 않는다.** 종료 코드가 1이어도 ⑤로 진행한다.

## ⑤ 완료 메시지 + 리포트 자동 오픈
- `daily_report.md`를 기본 프로그램으로 연다:
  ```
  start "" "daily_report.md"
  ```
  (Bash 도구에서는 `cmd //c start "" daily_report.md`)
- 아래 형식으로 완료 메시지를 출력한다:
```
✅ 완료
TOP 뉴스 N건 / 강세 X / 약세 Y / 중립 Z
리포트: daily_report.md
텔레그램: 성공/실패 (메시지 길이 N자)
사용한 가정: [있다면]
```

## 규칙
- 모든 분석·메시지에 "참고용이며 투자권유가 아님"을 명시한다. "사세요/파세요" 같은 표현은 금지.
- 실제 매매 주문, 외부 패키지 설치, 폴더 밖 파일 접근은 금지.
- `.env` 내용은 출력하거나 로그에 남기지 않는다.
