"""실거래가 수집: 국토교통부 아파트 매매 실거래가 API -> price_data.json

watch_config.json의 target_areas(동 단위)에 대해 최근 12개월 실거래를 모은다.
(최근 3개월 = 분석 대상 거래, 12개월 = 단지별 기준가 계산용)
API 키는 .env에서 읽는다 (코드에 하드코딩하지 않음). 표준 라이브러리만 사용.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))

# 법정동코드 앞 5자리(시군구)
LAWD_CODES = {"마포구": "11440", "강서구": "11500"}
PYEONG = 3.3058


def load_env():
    env = {}
    path = os.path.join(BASE, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


MONTHS = 12


def recent_months(n=MONTHS):
    t = date.today()
    y, m = t.year, t.month
    out = []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def fetch(endpoint, key, lawd, ymd):
    items, page = [], 1
    while True:
        # serviceKey는 urllib.parse.quote로 직접 인코딩 (특수문자 키 대응)
        q = f"serviceKey={urllib.parse.quote(key, safe='')}&" + urllib.parse.urlencode(
            {"LAWD_CD": lawd, "DEAL_YMD": ymd, "pageNo": page, "numOfRows": 1000})
        for attempt in range(2):  # 1회 재시도
            try:
                with urllib.request.urlopen(f"{endpoint}?{q}", timeout=30) as r:
                    root = ET.fromstring(r.read())
                break
            except Exception as e:
                if attempt == 1:
                    raise
                time.sleep(3)
        code = root.findtext(".//resultCode")
        if code not in ("00", "000"):
            raise RuntimeError(f"API 오류 {code}: {root.findtext('.//resultMsg')}")
        batch = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
        items += batch
        total = int(root.findtext(".//totalCount") or 0)
        if page * 1000 >= total or not batch:
            return items
        page += 1


def write_log(lines):
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    path = os.path.join(BASE, "logs", f"run_{datetime.now():%Y-%m-%d}.md")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n## price-collector {datetime.now():%H:%M:%S}\n" + "\n".join(f"- {l}" for l in lines) + "\n")


def complexes_summary(trades):
    """단지·면적대별 최근 거래가 요약 (trades는 최신순)"""
    out = {}
    for t in trades:
        k = (t["apt"], round(t["exclusive_m2"]))
        if k not in out:
            out[k] = {"apt": t["apt"], "exclusive_m2": t["exclusive_m2"],
                      "pyeong_supply_est": t["pyeong_supply_est"], "latest_price_억": t["price_억"],
                      "latest_date": t["date"], "latest_floor": t["floor"], "trade_count_12m": 0}
        out[k]["trade_count_12m"] += 1
    return list(out.values())


def main():
    """실패해도 전체를 멈추지 않는다: 실패한 지역은 기존 price_data.json 값을 유지하고 로그를 남긴 뒤 exit 0."""
    out_path = os.path.join(BASE, "price_data.json")
    try:
        previous = {a["area"]: a for a in json.load(open(out_path, encoding="utf-8")).get("areas", [])}
    except (OSError, ValueError):
        previous = {}

    env = load_env()
    key = env.get("DATA_GO_KR_API_KEY")
    endpoint = env.get("DATA_GO_KR_APT_TRADE_ENDPOINT",
                       "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade")
    if not key:
        msg = "data.go.kr API 키를 .env에 입력 후 다시 실행하세요 (기존 price_data.json 유지)"
        print(msg)
        write_log([msg])
        return
    cfg = json.load(open(os.path.join(BASE, "watch_config.json"), encoding="utf-8"))
    log = []
    unsupported = [t for t in cfg.get("property_types", ["아파트"]) if t != "아파트"]
    if unsupported:
        log.append(f"미지원 유형 건너뜀: {', '.join(unsupported)} (아파트 매매 API만 사용)")
    if "아파트" not in cfg.get("property_types", ["아파트"]):
        log.append("property_types에 아파트가 없어 수집하지 않음 (기존 파일 유지)")
        write_log(log)
        return
    min_m2 = cfg.get("min_size_평", 0) * PYEONG * 0.72  # 공급평형 -> 전용면적 근사(전용률 72%)

    result = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
              "months": recent_months(), "min_exclusive_m2": round(min_m2, 1),
              "areas": []}
    for area in cfg["target_areas"]:
        parts = area.split()
        gu, dong = parts[1], parts[2]
        if gu not in LAWD_CODES:
            log.append(f"{area}: 법정동코드 미등록 구({gu}) - LAWD_CODES에 추가 필요, 건너뜀")
            if area in previous:
                result["areas"].append(previous[area])
            continue
        trades, errors = [], []
        for ymd in result["months"]:
            try:
                for it in fetch(endpoint, key, LAWD_CODES[gu], ymd):
                    if it.get("umdNm") != dong or it.get("cdealType") == "O":  # 해제 거래 제외
                        continue
                    ar = float(it["excluUseAr"])
                    if ar < min_m2:
                        continue
                    price = int(it["dealAmount"].replace(",", ""))  # 만원
                    trades.append({
                        "apt": it["aptNm"], "exclusive_m2": ar,
                        "pyeong_supply_est": round(ar / 0.72 / PYEONG, 1),
                        "floor": int(it.get("floor") or 0), "build_year": int(it.get("buildYear") or 0),
                        "price_만원": price, "price_억": round(price / 10000, 2),
                        "price_per_m2_만원": round(price / ar, 1),
                        "date": f"{it['dealYear']}-{int(it['dealMonth']):02d}-{int(it['dealDay']):02d}",
                    })
            except Exception as e:
                errors.append(f"{ymd}: {e}")
        if errors and area in previous:
            # 한 달이라도 실패하면 데이터가 불완전하므로 이 지역은 기존 값을 유지
            kept = dict(previous[area], stale=True, errors=errors)
            result["areas"].append(kept)
            log.append(f"{area}: API 실패 {len(errors)}개월 → 기존 데이터 유지 ({errors[0]})")
            continue
        if errors:
            log.append(f"{area}: API 실패 {len(errors)}개월, 기존 데이터 없음 → 수집분만 저장")
        trades.sort(key=lambda t: t["date"], reverse=True)
        ppm = [t["price_per_m2_만원"] for t in trades]
        result["areas"].append({
            "area": area, "lawd_cd": LAWD_CODES[gu], "trade_count": len(trades),
            "avg_price_per_m2_만원": round(sum(ppm) / len(ppm), 1) if ppm else None,
            "complexes": complexes_summary(trades),
            "trades": trades,
            "listings": [],  # 매물 데이터 소스 미연동
            "errors": errors,
        })
        log.append(f"{area}: 실거래 {len(trades)}건, 단지·면적대 {len(result['areas'][-1]['complexes'])}개")

    if not any(a.get("trades") for a in result["areas"]) and previous:
        log.append("수집된 거래가 하나도 없음 → 기존 price_data.json 전체 유지")
    else:
        json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    write_log(log)
    print("\n".join(log))


if __name__ == "__main__":
    main()
