---
description: 쇼핑 가격 추적 워크플로 — 가격 수집 → 이력 기록 → 목표가 알림 → 추이 차트를 한 번에 실행
argument-hint: (인자 없음)
allowed-tools: Read, Write, Bash, WebSearch, WebFetch, mcp__tavily__tavily_search, mcp__tavily__tavily_extract
---

# price-track-workflow — 가격 추적 통합 워크플로

`watchlist.json`에 등록된 상품의 현재가를 수집하고, 이력 기록 · 목표가 알림 · 추이 차트까지 순서대로 실행한다.
확인 질문 없이 끝까지 진행하고, 마지막에 완료 메시지를 출력한다.

## 실행 트리거
| 방법 | 입력 |
|------|------|
| 자연어 | `지금 가격확인해줘` |
| 슬래시 명령어 | `/price-track-workflow` |

## 전체 흐름
```
watchlist.json
   │
   ▼ ① price-scraper   (웹 검색으로 현재가 조회)
scraped_prices.json
   │
   ▼ ② price-recorder  (python price_recorder.py)
prices.csv · price_stats.json
   │
   ├─▶ ③ price-alert   (python price_alert.py) ──▶ 텔레그램 · alert_history.json
   │
   └─▶ ④ price-chart   (python price_chart.py) ──▶ price_chart.html
   │
   ▼ ⑤ 완료 메시지
```

모든 명령은 이 프로젝트 폴더(`3.1-price-tracker`)에서 실행한다. 한글 출력이 깨지지 않도록 Bash에서는 `PYTHONIOENCODING=utf-8`을 붙인다.

---

## ① price-scraper — 현재가 수집
- 정의: `agents/price-scraper.md`를 읽고 그 규칙을 그대로 따른다.
- 먼저 현재 시각을 확인한다(추측 금지):
  `python -c "from datetime import datetime; print(datetime.now().astimezone().isoformat(timespec='seconds'))"`
  → 이 값을 `collected_at`으로 쓴다.
- `watchlist.json`의 `active: true` 상품만 순서대로 웹 검색해 국내 신품 최저가를 찾는다.
  - 필터: 중고·리퍼·액세서리·해외직구·카드 조건부 할인 제외
  - `expected_price`의 50% 미만 / 200% 초과면 1회 재검색 후 `PRICE_OUT_OF_RANGE`
  - 가능하면 `discount_info`, `stock_status`도 채운다.
- 결과를 `scraped_prices.json`에 **덮어쓴다**(실패 상품은 `price: null` + `error` + `error_message`).
- 산출물 확인: `scraped_prices.json`의 `summary`(total/success/failed)

**실패 시**: 모든 상품이 실패해도 파일은 저장하고 ②로 진행한다(②는 실패 상품을 기록하지 않는다).
`BLOCKED`(403/429, robots.txt 차단)가 나오면 해당 상품 수집을 즉시 중단하고 다음 회차로 미룬다.

## ② price-recorder — 이력 기록
- 정의: `agents/price-recorder.md`
- 실행: `PYTHONIOENCODING=utf-8 python price_recorder.py`
- 결과: `prices.csv`에 새 행 추가(전일대비변동 계산, 중복 방지), `price_stats.json` 갱신
- 확인: 출력의 "N행 기록" 문구

**실패 시**: 스크립트 오류면 워크플로를 중단하고 오류 내용을 보고한다(③④는 ②의 결과에 의존).

## ③ price-alert — 목표가 확인 및 알림
- 정의: `agents/price-alert.md`
- 실행: `PYTHONIOENCODING=utf-8 python price_alert.py`
- 조건: 목표가 달성(수집가 ≤ 목표가) → `[최저가알림]`, 미달성이지만 직전 대비 10% 이상 하락 → `[가격하락]`
- 중복 방지 없음: 조건을 충족하면 실행할 때마다 발송한다.
- 결과: 텔레그램 발송, `alert_history.json`에 누적 기록
- 확인: 출력의 "알림: K/N건 발송"

**실패 시**: 텔레그램 발송 실패(1회 재시도 후)는 기록만 남기고 ④로 계속 진행한다.

## ④ price-chart — 추이 차트 갱신
- 정의: `agents/price-chart.md`
- 실행: `PYTHONIOENCODING=utf-8 python price_chart.py`
- 결과: `price_chart.html` 갱신(요약 카드, 상품별 선 그래프, 최근 변동 10건)

**실패 시**: 오류를 보고에 포함하고 ⑤로 진행한다.

## ⑤ 완료 메시지
아래 한 줄을 **반드시** 출력한다.
```
수집완료 - [YYYY-MM-DD HH:MM] / 추적 중 상품 N개
```
- `[YYYY-MM-DD HH:MM]`: ①의 `collected_at`(KST)
- `N`: `watchlist.json`에서 `active: true`인 상품 수

그 아래에 단계별 결과를 간단히 붙인다.
```
수집: S/T개 성공 (실패: prd-xxx PRICE_NOT_FOUND …)
기록: prices.csv +R행
알림: K건 발송 (상품명 [유형] …)
차트: price_chart.html
```

## 금지 사항
- 자동 구매·결제·장바구니 담기 금지
- 외부 패키지 설치 금지(표준 라이브러리 + 웹 검색 도구만 사용)
- `.env`의 값(토큰·채팅 ID)을 출력하거나 다른 파일에 옮기지 않는다.
- 이 프로젝트 폴더 밖의 파일은 건드리지 않는다.
