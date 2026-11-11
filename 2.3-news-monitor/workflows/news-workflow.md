# news-workflow — 데일리 뉴스·채용 브리핑 통합 워크플로우

에이전트 4개를 순서대로 실행해 텔레그램 아침 브리핑을 보낸다.

## 트리거
| 방식 | 조건 |
|------|------|
| **수동** | 사용자가 **`지금 브리핑 보내줘`**를 입력하면 확인 질문 없이 즉시 1~5단계를 실행한다 |
| 자동 | 매일 오전 8:00 (`run_schedule.bat`, 스케줄 등록 단계에서 설정) |

## 실행 순서
```
[1] news-collector ──▶ collected_news.json ──┐   (실패 시 전날 캐시로 대체)
                                             ▼
[2] impact-analyzer ─────────────────▶ analyzed_news.json
[3] job-collector ───────────────────▶ collected_jobs.json
                                             ▼
[4] newsletter-sender ──▶ 텔레그램 발송 ──▶ newsletter_log.json, logs/briefing_YYYY-MM-DD.md
                                             ▼
[5] 완료 메시지 출력
```

| 단계 | 에이전트 정의 | 입력 | 출력 |
|------|---------------|------|------|
| 1 | `agents/news-collector.md` | `monitor_config.json` (news_keywords) | `collected_news.json` + `cache/collected_news_YYYY-MM-DD.json` |
| 2 | `agents/impact-analyzer.md` | `collected_news.json` | `analyzed_news.json` |
| 3 | `agents/job-collector.md` | `monitor_config.json` (job_keywords, job_filters) | `collected_jobs.json` |
| 4 | `agents/newsletter-sender.md` | `analyzed_news.json`, `collected_jobs.json`, `upcoming_events.json` | 텔레그램 메시지, `newsletter_log.json` |
| 5 | (워크플로우) | `newsletter_log.json` 마지막 항목 | 완료 메시지 |

- 3단계(채용 수집)는 1·2단계와 서로 의존하지 않는다. 하지만 하나의 흐름으로 보이도록 순서대로 실행한다.
- 각 단계는 앞 단계의 출력 파일이 **이번 실행에서 새로 만들어졌는지**(수정 시각) 확인한 뒤 시작한다.

## 단계별 상세

### 1. news-collector
- `agents/news-collector.md`의 규칙대로 수집한다 (24시간, 키워드당 5건, 제목 유사도 80% 중복 제거).
- **성공**(1건 이상 수집)하면 결과를 `cache/collected_news_YYYY-MM-DD.json`으로 복사한다. 7일이 지난 캐시는 지운다.

### 2. impact-analyzer
- `collected_news.json`의 모든 기사를 Claude가 분석한다 (영향도, 30자 요약, 높음 기사의 시사점).
- 결과는 높음 → 보통 → 낮음 순으로 정렬해 `analyzed_news.json`에 저장한다.

### 3. job-collector
- 사람인·원티드·링크드인·잡플래닛에서 48시간 이내 공고를 찾고, 경력·지역·제외 키워드 필터와 중복 제거를 적용한다.
- 0건이어도 실패가 아니다. 다음 단계에서 "오늘은 새 공고가 없습니다"로 표시된다.

### 4. newsletter-sender
- `collected_news.json`에서 예정 이벤트를 골라 `upcoming_events.json`을 만든다.
- `python newsletter_sender.py --dry-run`으로 메시지를 확인한 뒤 `python newsletter_sender.py`로 발송한다.
  - 이 프로젝트에서는 `.env` 접근을 보안 훅이 막는다. Claude Code 안에서 실행할 때는 사용자에게 `! python newsletter_sender.py` 실행을 요청한다.

### 5. 완료 메시지
발송이 성공하면 스크립트가 다음 형식으로 출력한다.
```
브리핑 발송완료 - 뉴스 {N}건 / 채용 {N}건 / {YYYY-MM-DD HH:MM}
```
- 뉴스 N = `analyzed_news.json`의 기사 수, 채용 N = 조건을 통과한 공고 수

## 예외 처리
| 상황 | 대응 |
|------|------|
| **뉴스 수집 실패** (검색 도구 오류, 또는 모든 키워드 0건) | `cache/`에서 가장 최근 날짜의 `collected_news_*.json`(전날 캐시)을 `collected_news.json`으로 복사해 2단계를 계속한다. 그 파일에 `"from_cache": true`, `"cache_date": "YYYY-MM-DD"`를 추가하고, 브리핑 헤더 아래에 `(어제 수집 데이터 사용)`을 표시한다 |
| 전날 캐시도 없음 | 뉴스 섹션 없이 채용공고만 발송한다 (뉴스 0건이면 섹션 생략) |
| 일부 키워드만 수집 실패 | 성공한 키워드만 사용한다. 실패한 키워드는 `collected_news.json`에 에러와 함께 기록된다 |
| 영향도 분석 실패 (특정 기사) | 그 기사는 `impact_level: "보통"`으로 채우고 계속한다 |
| 채용공고 수집 실패 | `status: "failed"`로 기록하고 "오늘은 새 공고가 없습니다"로 발송한다 |
| **텔레그램 발송 실패** | **3분(180초) 후 1회 재시도**한다 (`telegram.retry_delay_seconds: 180`, `retry_on_failure: 1`). 그래도 실패하면 `newsletter_log.json`에 `failed`와 오류를 기록하고 종료한다 |
| 토큰·chat_id 누락 | 발송하지 않고 로그에 원인을 남긴 뒤 종료한다 |

## 산출물
| 파일 | 설명 |
|------|------|
| `collected_news.json` | 1단계 뉴스 원문 |
| `cache/collected_news_YYYY-MM-DD.json` | 뉴스 일별 캐시 (7일 보관) |
| `analyzed_news.json` | 2단계 영향도 분석 결과 |
| `collected_jobs.json` | 3단계 채용공고 |
| `upcoming_events.json` | 4단계 "내일 주목할 것" 일정 |
| `newsletter_log.json` | 발송 이력 (30일 보관) |
| `logs/briefing_YYYY-MM-DD.md` | 발송 메시지 백업 (30일 보관) |
