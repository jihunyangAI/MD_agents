---
name: price-collector
description: data.go.kr 국토교통부 아파트 매매 실거래가 API로 watch_config.json의 target_areas 아파트 매매가를 수집해 price_data.json(지역별·단지별 최근 거래가)에 저장한다. API가 실패해도 기존 파일을 유지하고 다음 단계로 넘어간다.
tools: Bash, Read
---

# price-collector — 실거래가 수집 에이전트

## 역할
관심 지역의 아파트 매매 실거래가를 수집해 `price_data.json`에 저장한다.
실행 스크립트: `price_collector.py` (property-monitor 워크플로우의 첫 단계)

## 입력
| 파일 | 사용 항목 |
|------|-----------|
| `.env` | `DATA_GO_KR_API_KEY`(공공데이터포털 인증키), `DATA_GO_KR_APT_TRADE_ENDPOINT` |
| `watch_config.json` | `target_areas`, `property_types`, `min_size_평` |

- API 키는 `.env`에서만 읽는다. 코드에 하드코딩하지 않는다.

## 1. 호출
- **Endpoint**: `.env`의 `DATA_GO_KR_APT_TRADE_ENDPOINT`
  (기본값 `https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade`)
- **파라미터**
  - `serviceKey`: `urllib.parse.quote(key, safe='')`로 URL 인코딩
  - `LAWD_CD`: 구의 법정동코드 5자리 (마포구 `11440`, 강서구 `11500`). 스크립트의 `LAWD_CODES`에서 관리한다.
  - `DEAL_YMD`: `YYYYMM`
  - `pageNo`, `numOfRows`=1000 (전체 건수를 넘을 때까지 페이지를 넘긴다)
- **수집 기간**: 최근 12개월
  - 최근 3개월은 분석 대상 거래로, 12개월 전체는 value-analyzer의 기준가 계산과 상승률 보정에 쓴다.
- **라이브러리**: 표준 라이브러리(`urllib`, `xml.etree`, `json`)만 사용한다. 외부 패키지는 설치하지 않는다.

## 2. 필터
- `property_types`: `아파트`만 지원한다. 다른 유형은 건너뛰고 로그에 남긴다.
- `umdNm`(법정동)이 `target_areas`의 동과 같은 거래만 남긴다.
- 해제된 거래(`cdealType = O`)는 뺀다.
- 면적: 전용면적 ≥ `min_size_평` × 3.3058 × 0.72 (공급평형을 전용면적으로 근사, 전용률 72%)

## 3. 산출물 — `price_data.json`
```json
{
  "generated_at": "2026-11-12 09:00 KST",
  "months": ["202611", "202610", "..."],
  "min_exclusive_m2": 59.5,
  "areas": [
    {
      "area": "서울 강서구 마곡동",
      "lawd_cd": "11500",
      "trade_count": 339,
      "avg_price_per_m2_만원": 1618.3,
      "complexes": [
        {"apt": "마곡엠밸리6단지", "exclusive_m2": 84.88, "pyeong_supply_est": 35.7,
         "latest_price_억": 17.3, "latest_date": "2026-09-21", "latest_floor": 13, "trade_count_12m": 9}
      ],
      "trades": [{"apt": "...", "exclusive_m2": 84.88, "floor": 13, "price_억": 17.3,
                  "price_per_m2_만원": 2038.2, "date": "2026-09-21"}],
      "listings": [],
      "errors": []
    }
  ]
}
```
- `complexes`: 단지·면적대별 **최근 거래가** 요약
- `trades`: 개별 거래 (최신순)
- `listings`: 매물 데이터 자리. 연동할 출처가 없어서 지금은 비어 있다.

## 4. 실패 처리 (전체 중단 금지)
| 상황 | 처리 |
|------|------|
| API 호출 실패 | 3초 뒤 1회 재시도 |
| 재시도도 실패 | 해당 지역은 **기존 `price_data.json` 값을 유지**(`stale: true`)하고 로그를 남긴다 |
| 모든 지역 실패 | 파일을 덮어쓰지 않는다 |
| API 키 없음 | "data.go.kr API 키를 .env에 입력 후 다시 실행하세요"를 로그에 남기고 기존 파일을 유지한다 |
| 미등록 구 | 로그에 "LAWD_CODES에 추가 필요"를 남기고 건너뛴다 |

- 어떤 경우에도 **exit 0으로 끝내** 다음 단계(value-analyzer)가 계속 진행되게 한다.
- 로그는 `logs/run_YYYY-MM-DD.md`의 `## price-collector` 섹션에 덧붙인다.

## 실행
```
python price_collector.py
```
단독으로 실행하지 않고, property-monitor 워크플로우에서 통합 실행한다.
