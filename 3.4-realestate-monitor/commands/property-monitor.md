---
description: 실거래 수집 → 교통·학군·정책 분석 → 미래 가치 종합 → 텔레그램 알림까지 한 번에 실행하는 property-monitor 워크플로
allowed-tools: Bash, Read, Write, WebSearch, WebFetch
---

# property-monitor — 부동산 미래 가치 모니터링 통합 워크플로

## 수동 실행 트리거 (둘 다 같은 동작)
- 슬래시 명령어: `/property-monitor`
- 자연어: **"지금 매물 한번 분석해줘"**

확인 질문 없이 아래 6단계를 **순서대로** 즉시 실행한다.
- 작업 폴더: 프로젝트 루트 (`3.4-realestate-monitor`)
- 설정: `watch_config.json` (target_areas, max_price_억, min_size_평, alert_score_threshold, telegram_alert)
- Python 명령은 `PYTHONIOENCODING=utf-8`을 붙여 실행한다 (Windows 콘솔 한글 깨짐 방지).

**공통 실패 원칙**: 한 단계가 실패해도 전체를 멈추지 않는다. 실패한 단계는 기존 산출물을 그대로 두고, `logs/run_YYYY-MM-DD.md`에 기록한 뒤 다음 단계로 넘어간다.

---

## 1단계 — price-collector (`agents/price-collector.md`)
```
PYTHONIOENCODING=utf-8 python price_collector.py
```
- 국토부 실거래가 API로 최근 12개월 아파트 매매가를 수집한다 → `price_data.json`
- API가 실패하면 1회 재시도하고, 그래도 실패하면 기존 `price_data.json`을 유지한다 (스크립트가 exit 0으로 끝남).

## 2단계 — transport-analyzer (`agents/transport-analyzer.md`)
- 에이전트 정의를 읽고 그 절차대로 **웹 검색으로 직접 수행**한다 (스크립트 없음).
- 지역별 교통 호재(지하철 연장, GTX, 도로, 버스노선, 트램)를 수집하고 0~30점을 매긴다 → `transport_score.json`
- 실패하면 기존 `transport_score.json`을 유지한다.

## 3단계 — school-info-collector (`agents/school-info-collector.md`)
- 나이스 `schoolInfo` API(`.env`의 `NEIS_API_KEY`)로 학교 목록을 받고, 웹 검색으로 진학률을 확인한다.
- 0~20점을 매긴다 → `school_score.json`
- 학군은 자주 바뀌지 않는다. 기존 `school_score.json`이 **30일 이내**면 이 단계를 건너뛰고 "학군: 기존 결과 사용"이라고 출력한다.

## 4단계 — policy-monitor (`agents/policy-monitor.md`)
- 에이전트 정의대로 국토부, 서울시 도시계획 포털, 네이버 뉴스를 검색한다.
- 정책 영향도를 -10~+20점으로 매긴다 → `policy_score.json`
- 실패하면 기존 `policy_score.json`을 유지한다.

> 2~4단계는 웹 검색 비용이 크다. 자동 스케줄(6시간 주기)로 실행될 때는 산출물의 `generated_at`이 **24시간 이내면 그 단계를 건너뛴다**. 수동 트리거로 실행할 때는 항상 새로 분석한다.

## 5단계 — value-analyzer (`agents/value-analyzer.md`)
```
PYTHONIOENCODING=utf-8 python value_analyzer.py --no-alert
```
- 1~4단계 산출물을 합쳐 단지별 미래 가치 점수(100점 만점)를 계산한다.
  - 시세 30: 같은 단지 12개월 평균 대비 저렴한 정도, 지역 상승률로 보정
  - 교통 30 / 학군 20 / 정책 20
- 결과에 의견(적극매수/관망/보류, 참고용)을 붙여 `value_report.json`에 저장한다.
- `--no-alert`: 알림은 6단계에서 따로 실행한다 (중복 실행 방지).
- 점수 파일이 없으면 남은 항목으로 정규화해서 계속 진행한다.

## 6단계 — telegram-alert (`agents/telegram-alert.md`)
```
PYTHONIOENCODING=utf-8 python telegram_alert.py
```
- 조건: **최종점수 ≥ alert_score_threshold AND 가격 ≤ max_price_억**
- 같은 매물은 7일 안에 1번만 보낸다 (`alert_state.json`).
- 모든 메시지에 면책 문구를 넣는다.
- 조건을 충족한 매물이 없으면 보내지 않고 로그에만 기록한다.
- 테스트할 때는 `--dry-run`으로 미리보기만 한다.

---

## 완료 보고 (콘솔 출력)
```
✅ 완료
실거래 N건 / 신규 매물 M건 / 매력 매물 K건
알림: 발송 X건
사용한 가정: [있다면]
```
- 실거래 N: `price_data.json`의 지역별 `trade_count` 합
- 신규 매물 M: `listings` 합. 매물 데이터가 연동되지 않았으면 0이고, "최근 실거래로 대체"를 가정에 적는다.
- 매력 매물 K: `value_report.json`의 `alert_candidates` 수
- 발송 X: 6단계 로그의 발송 건수
- 단계별 점수 요약표(지역 × 교통/학군/정책/최고 단지 점수)를 함께 보여준다.
- 마지막 줄에 "본 분석은 참고용이며 투자 판단은 본인 책임입니다."를 넣는다.

## 로그
- 모든 단계 결과는 `logs/run_YYYY-MM-DD.md`에 덧붙인다. 90일이 지난 로그는 삭제한다.
- 실제 매수, 계약, 중개사 연결 같은 행동은 하지 않는다.
