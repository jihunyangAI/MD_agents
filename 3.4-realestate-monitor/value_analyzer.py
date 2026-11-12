"""미래 가치 분석: price_data + transport/school/policy 점수 -> value_report.json

최종점수(100) = 시세점수(30) + 교통(30) + 학군(20) + 정책(20, -10~+20)
매물 데이터가 없으면 단지별 '최근 실거래 ㎡당가'를 같은 단지 12개월 평균과 비교한다(대체 지표).
기준가의 과거 거래는 지역 월간 상승률로 비교 시점까지 보정한다(상승장 편향 제거).
분석이 끝나면 telegram_alert.py가 있으면 실행한다(telegram-alert 에이전트).
"""
import json
import math
import os
import subprocess
import sys
from datetime import date, datetime


def month_pos(d):
    """'YYYY-MM-DD' -> 월 단위 연속값"""
    y, m, dd = map(int, d.split("-"))
    return y * 12 + (m - 1) + (dd - 1) / 30.44


def area_monthly_growth(trades):
    """단지·면적대 고정효과 회귀(within estimator)로 지역 월간 ㎡당가 상승률을 추정한다.
    서로 다른 단지 구성 차이를 없애고 '같은 집이 시간에 따라 얼마나 올랐나'만 본다."""
    groups = {}
    for t in trades:
        groups.setdefault((t["apt"], round(t["exclusive_m2"] / 5)), []).append(
            (month_pos(t["date"]), math.log(t["price_per_m2_만원"])))
    num = den = 0.0
    n = 0
    for pts in groups.values():
        if len(pts) < 2:
            continue
        tb = sum(p[0] for p in pts) / len(pts)
        yb = sum(p[1] for p in pts) / len(pts)
        for x, y in pts:
            num += (x - tb) * (y - yb)
            den += (x - tb) ** 2
            n += 1
    if den == 0 or n < 10:
        return 0.0, n
    g = math.exp(num / den) - 1
    return max(-0.03, min(0.03, g)), n  # 월 ±3%로 제한(이상치 방지)

BASE = os.path.dirname(os.path.abspath(__file__))
DISCLAIMER = "본 분석은 참고용이며 투자 판단은 본인 책임입니다."


def load(name, default=None):
    p = os.path.join(BASE, name)
    if not os.path.exists(p):
        return default
    return json.load(open(p, encoding="utf-8"))


def by_area(data):
    return {a["area"]: a for a in (data or {}).get("areas", [])}


def price_score(discount_pct):
    """discount_pct: 평균 대비 저렴한 비율(%). 양수=저렴."""
    d = discount_pct
    if d >= 10:
        return round(min(30, 25 + (d - 10) / 2))
    if d >= 5:
        return round(15 + (d - 5) / 5 * 9)
    if d > -5:
        return round(5 + (d + 5) / 10 * 9)  # 평균 수준: 5~14
    return max(0, round(4 + (d + 5) / 2))   # 고평가: 0~4


def opinion(total, threshold):
    if total >= 70:
        return "적극매수"
    if total >= threshold:
        return "관망"
    return "보류"


def main():
    cfg = load("watch_config.json")
    price = by_area(load("price_data.json"))
    tr, sc, po = by_area(load("transport_score.json")), by_area(load("school_score.json")), by_area(load("policy_score.json"))
    threshold = cfg.get("alert_score_threshold", 70)
    max_price = cfg.get("max_price_억", 999)

    report = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
              "formula": "시세(30) + 교통(30) + 학군(20) + 정책(-10~+20) = 100점 만점",
              "alert_rule": f"점수 >= {threshold} AND 가격 <= {max_price}억",
              "disclaimer": DISCLAIMER, "areas": [], "alert_candidates": []}

    for area in cfg["target_areas"]:
        p = price.get(area, {})
        t = (tr.get(area) or {}).get("score")
        s = (sc.get(area) or {}).get("score")
        pol = (po.get(area) or {}).get("score")
        avg = p.get("avg_price_per_m2_만원")
        notes = []

        # 단지별: 매물이 있으면 매물가, 없으면 단지 최근 실거래로 대체
        items = []
        source = "listings" if p.get("listings") else "latest_trade_proxy"
        months = sorted((load("price_data.json") or {}).get("months", []))
        recent_from = f"{months[-3][:4]}-{months[-3][4:]}-01" if len(months) >= 3 else "0000-00-00"
        if source == "latest_trade_proxy":
            notes.append("매물 데이터 미연동: 최근 3개월 내 단지별 최신 실거래가를 같은 단지·면적대의 "
                         "직전 12개월 평균(해당 거래 제외)과 비교(대체 지표). 비교 거래 2건 미만이면 '평균 수준'")
            latest = {}
            for tr_ in p.get("trades", []):  # 최신순 정렬됨
                if tr_["date"] < recent_from:
                    continue
                k = (tr_["apt"], round(tr_["exclusive_m2"]))
                latest.setdefault(k, tr_)
            items = list(latest.values())
        else:
            items = p["listings"]

        missing = [n for n, v in (("교통", t), ("학군", s), ("정책", pol)) if v is None]
        if missing:
            notes.append(f"점수 누락({', '.join(missing)}): 가용 항목 비중으로 정규화")

        growth, growth_n = area_monthly_growth(p.get("trades", []))
        notes.append(f"지역 상승률 보정: 월 {growth * 100:+.2f}% (연 {((1 + growth) ** 12 - 1) * 100:+.1f}%, "
                     f"동일 단지 반복 거래 {growth_n}건으로 추정)")

        # 기준가: 같은 단지·같은 면적대(±5㎡) 12개월 실거래 ㎡당가를 비교 시점으로 상승률 보정한 평균
        # (비교 대상 거래 자신은 제외, 2건 이상)
        def baseline(it):
            target = month_pos(it.get("date") or date.today().isoformat())
            same = [x["price_per_m2_만원"] * (1 + growth) ** (target - month_pos(x["date"]))
                    for x in p.get("trades", [])
                    if x is not it and x["apt"] == it["apt"]
                    and abs(x["exclusive_m2"] - it["exclusive_m2"]) <= 5]
            return (sum(same) / len(same), len(same)) if len(same) >= 2 else (None, len(same))

        results = []
        for it in items:
            ppm = it["price_per_m2_만원"]
            base, n = baseline(it)
            disc = round((base - ppm) / base * 100, 1) if base else 0.0  # 비교 불가 시 평균 수준
            ps = price_score(disc)
            parts = {"price": ps, "transport": t, "school": s, "policy": pol}
            maxes = {"price": 30, "transport": 30, "school": 20, "policy": 20}
            got = {k: v for k, v in parts.items() if v is not None}
            raw = sum(got.values())
            denom = sum(maxes[k] for k in got)
            total = round(max(0, min(100, raw * 100 / denom))) if denom else None
            row = {"apt": it["apt"], "exclusive_m2": it["exclusive_m2"],
                   "pyeong_supply_est": it.get("pyeong_supply_est"), "floor": it.get("floor"),
                   "price_억": it["price_억"], "date": it.get("date"),
                   "baseline_price_per_m2_만원": round(base, 1) if base else None,
                   "baseline_trades": n,
                   "discount_vs_avg_pct": disc if base else None, "scores": parts, "total": total,
                   "opinion": opinion(total, threshold),
                   "within_budget": it["price_억"] <= max_price}
            results.append(row)
            if total >= threshold and row["within_budget"]:
                report["alert_candidates"].append({"area": area, **row,
                                                   "id": f"{area}|{it['apt']}|{it['exclusive_m2']}|{it.get('floor')}"})
        results.sort(key=lambda r: r["total"], reverse=True)
        report["areas"].append({
            "area": area, "avg_price_per_m2_만원": avg, "trade_count": p.get("trade_count", 0),
            "price_basis": source, "monthly_growth_pct": round(growth * 100, 2), "area_scores": {"transport": t, "school": s, "policy": pol},
            "complexes": results, "notes": notes})

    report["alert_candidates"].sort(key=lambda r: r["total"], reverse=True)
    json.dump(report, open(os.path.join(BASE, "value_report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    for a in report["areas"]:
        top = a["complexes"][0] if a["complexes"] else None
        print(f"{a['area']}: 단지 {len(a['complexes'])}개, 최고 {top['apt'] if top else '-'} {top['total'] if top else '-'}점")
    print(f"알림 후보 {len(report['alert_candidates'])}건")

    alert = os.path.join(BASE, "telegram_alert.py")
    if "--no-alert" in sys.argv:
        print("--no-alert: 알림은 워크플로 6단계에서 실행")
    elif os.path.exists(alert):
        subprocess.run([sys.executable, alert], cwd=BASE)
    else:
        print("telegram_alert.py 없음: 알림 단계 건너뜀")


if __name__ == "__main__":
    main()
