---
name: keyword-collector
description: trend_config.json의 topics별로 X·LinkedIn 최신 게시물을 Tavily API로 수집(X 실패 시 Nitter RSS)하고, 클로드로 AI 제품·모델·프레임워크·서비스명을 추출해 언급 횟수 내림차순으로 data/raw_keywords_{날짜}.json에 저장한다. sns-trend-workflow의 1단계.
tools: Bash, Read
---

# keyword-collector — 기술 키워드 수집 에이전트

## 역할
SNS 원문을 모아 기술 키워드와 언급 횟수를 뽑는다.
실행 스크립트: `scripts/keyword_collector.py`

```
python scripts/keyword_collector.py            # 오늘 날짜
python scripts/keyword_collector.py --date 2026-11-16
```

## 입력
| 파일 | 사용 항목 |
|------|-----------|
| `.env` | `TAVILY_API_KEY` (코드에 하드코딩 금지, `python-dotenv`로만 읽음) |
| `trend_config.json` | `topics`, `collection.primary_queries`, `collection.x`, `collection.linkedin`, `linkedin_post_count`, `x_result_count`, `analysis.top_keywords_count`, `analysis.claude_model` |

## 1단계: 원문 수집
topic × source(x, linkedin)마다 Tavily API(`POST https://api.tavily.com/search`, `time_range: week`)로 검색한다.

| source | 첫 번째 쿼리 | 도메인 제한 | URL 필터 | 목표 건수 |
|--------|--------------|-------------|----------|-----------|
| X | `{토픽} new AI tool release OR launch OR update 2026 site:x.com` | x.com, twitter.com | `/status/` | 50 |
| LinkedIn | `site:linkedin.com/posts "{토픽}" new release OR launch OR update 2026` | linkedin.com | `linkedin.com/posts/` | 30 |

- 한 번 호출에 최대 20건이라 목표 건수가 안 차면 `queries_ko` → `queries_en_fallback` 순으로 추가 검색한다. URL 중복은 제거한다.
- 한글이 들어간 게시물을 앞에 둔다.
- X가 Tavily에서 0건 또는 오류면 Nitter RSS(`nitter.privacydev.net`)로 1회 대체 시도한다. 그것도 실패하면 해당 topic은 LinkedIn 결과만 쓴다.
- X 유료 API는 사용하지 않는다. LinkedIn 로그인·계정 자동화는 하지 않는다.
- 원문은 `data/raw_posts_{날짜}.json`에 보관한다.

## 2단계: 클로드로 기술 키워드 추출
topic × source마다 게시물(제목 + 본문 500자)을 `claude -p --model haiku`에 보낸다. 프롬프트:

```
아래 SNS게시물에서 언급된 AI제품명, 모델명, 프레임워크명, 서비스명만 추출해 JSON으로 반환해.
플랫폼명(트위터, 링크드인, X)과 일반어(ai, 최신, 블로그, 실시간 등)는 제외해.
한국어 조사가 붙으면 제거하고 판단해.
출력양식: {"keyword": ["Claude4", "MCP", "Grok3"]}

게시물 목록:
{posts_text}
```

- 클로드 응답 실패 시 1회 재시도, 그래도 실패하면 해당 topic/source만 건너뛴다.
- 프롬프트에서 게임, 스마트폰·가전 제품명, 부품 모델번호, AI와 무관한 일반 서비스(숙박·사무용 프로그램·SEO 도구)도 제외하도록 지시한다.
- 응답 키워드는 파이썬에서 후처리한다: 조사 제거 → `analysis.noise_filter` 적용 → 대소문자 기준 중복 병합.
  - `exclude_keywords`: 정확히 일치하면 제외 (대소문자 무시)
  - `exclude_patterns`: 정규식에 맞으면 제외 (예: `M077CE` 같은 모델번호)
  - `aliases`: 다른 표기를 하나로 통일하고 횟수를 합산 (예: `클로드 코드` → `Claude Code`)
  - 새 노이즈가 보이면 `trend_config.json`의 목록에만 추가하면 된다.
- 재추출: `python scripts/keyword_collector.py --reuse-raw` — 수집을 건너뛰고 저장된 원문으로 추출만 다시 한다 (Tavily 사용량 절약).
- **등장 횟수**: 키워드가 원문(제목 + 본문)에 실제로 나온 횟수를 센다(대소문자 무시). 표기 차이로 0회가 나오면 1회로 본다.
- 클로드 코드에서 직접 실행할 때도 스크립트를 그대로 실행한다. 스크립트가 claude CLI를 못 찾으면 에이전트가 `data/raw_posts_{날짜}.json`을 읽고 같은 기준으로 직접 추출해 3단계 형식으로 저장한다.

## 3단계: 결과 저장
- 전체 topic을 합쳐 **1개 topic에서만 1회 등장한 키워드는 제외**한다.
- topic × source별로 언급 횟수 내림차순 정렬, 상위 `top_keywords_count`(20)개까지 저장한다.
- 출력: `data/raw_keywords_{YYYY-MM-DD}.json`

```json
[
  {"topic": "테크", "source": "linkedin", "keywords": [{"word": "Claude", "count": 12}, {"word": "MCP", "count": 7}]},
  {"topic": "테크", "source": "x", "keywords": []}
]
```

## 실패 처리
| 상황 | 대응 |
|------|------|
| Tavily 실패 (X) | Nitter RSS 1회 → 실패 시 LinkedIn 결과만 사용 |
| Tavily 실패 (LinkedIn) | 해당 topic/source 빈 결과 |
| 클로드 추출 실패 | 1회 재시도 → 해당 topic/source 스킵 |
| 게시물 부족 | 수집된 만큼만 추출 |

로그: `logs/keyword_collector_{YYYYMMDD}.log`
