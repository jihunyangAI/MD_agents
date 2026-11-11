"""price-recorder: scraped_prices.json -> prices.csv 누적 기록 + 상품별 가격 통계.

표준 라이브러리만 사용한다.
실행: python price_recorder.py
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCRAPED = BASE / "scraped_prices.json"
WATCHLIST = BASE / "watchlist.json"
CSV_PATH = BASE / "prices.csv"
STATS_PATH = BASE / "price_stats.json"
ENCODING = "utf-8-sig"  # UTF-8 + BOM: 엑셀에서 한글이 깨지지 않게

HEADER = [
    "수집일시", "상품ID", "상품명", "수집가격(원)", "목표가격(원)",
    "목표달성여부", "할인정보", "재고상태", "전일대비변동(원)",
]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_rows():
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, encoding=ENCODING, newline="") as f:
        return list(csv.DictReader(f))


def fmt_time(iso):
    return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")


def fmt_change(diff):
    if diff is None:
        return "-"
    return f"{diff:+d}" if diff else "0"


def record(scraped, watch, rows):
    """새 행 목록을 만든다. 실패 상품은 건너뛴다(빈 행 금지)."""
    collected = fmt_time(scraped["collected_at"])
    existing = {(r["수집일시"], r["상품ID"]) for r in rows}
    last_price = {}
    for r in rows:  # 상품별 직전 수집가격
        last_price[r["상품ID"]] = int(r["수집가격(원)"])

    new_rows, skipped = [], []
    for res in scraped["results"]:
        pid = res["id"]
        if not res.get("success") or res.get("price") is None:
            skipped.append(f"{pid} 수집 실패({res.get('error')}) - 기록 생략")
            continue
        if (collected, pid) in existing:
            skipped.append(f"{pid} {collected} 이미 기록됨 - 중복 생략")
            continue
        price = int(res["price"])
        target = watch.get(pid, {}).get("target_price")
        prev = last_price.get(pid)
        new_rows.append({
            "수집일시": collected,
            "상품ID": pid,
            "상품명": res.get("name") or watch.get(pid, {}).get("name", ""),
            "수집가격(원)": price,
            "목표가격(원)": target if target is not None else "",
            "목표달성여부": "Y" if target is not None and price <= target else "N",
            "할인정보": res.get("discount_info") or "-",
            "재고상태": res.get("stock_status") or "확인불가",
            "전일대비변동(원)": fmt_change(None if prev is None else price - prev),
        })
        last_price[pid] = price
    return new_rows, skipped


def append_rows(new_rows):
    is_new = not CSV_PATH.exists()
    with open(CSV_PATH, "a", encoding=ENCODING, newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        if is_new:
            w.writeheader()
        w.writerows(new_rows)
    return is_new


TREND_DAYS = 7


def parse_time(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def trend_7d(items):
    """최근 수집 시점 기준 7일 안의 첫 가격과 마지막 가격을 비교한다."""
    latest_t = parse_time(items[-1]["수집일시"])
    window = [i for i in items
              if (latest_t - parse_time(i["수집일시"])).days < TREND_DAYS]
    if len(window) < 2:
        return "판단불가", 0, len(window)
    diff = int(window[-1]["수집가격(원)"]) - int(window[0]["수집가격(원)"])
    return ("하락" if diff < 0 else "상승" if diff > 0 else "유지"), diff, len(window)


def build_stats(rows, watch):
    stats = {}
    for r in rows:
        stats.setdefault(r["상품ID"], []).append(r)
    out = []
    for pid, items in stats.items():
        prices = [int(i["수집가격(원)"]) for i in items]
        low, high = min(prices), max(prices)
        latest = prices[-1]
        target = watch.get(pid, {}).get("target_price")
        trend, trend_diff, trend_n = trend_7d(items)
        out.append({
            "id": pid,
            "name": items[-1]["상품명"],
            "count": len(prices),
            "latest": latest,
            "latest_at": items[-1]["수집일시"],
            "previous": prices[-2] if len(prices) > 1 else None,
            "change_from_previous": latest - prices[-2] if len(prices) > 1 else None,
            "all_time_low": low,
            "all_time_low_at": next(i["수집일시"] for i in items if int(i["수집가격(원)"]) == low),
            "all_time_high": high,
            "all_time_high_at": next(i["수집일시"] for i in items if int(i["수집가격(원)"]) == high),
            "average": round(sum(prices) / len(prices)),
            "target": target,
            "remaining_to_target": None if target is None else max(0, latest - target),
            "target_reached": target is not None and latest <= target,
            "trend_7d": trend,
            "trend_7d_change": trend_diff,
            "trend_7d_samples": trend_n,
        })
    return {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "products": out}


def won(n):
    return f"{n:,}원"


def main():
    if not SCRAPED.exists():
        sys.exit("scraped_prices.json 이 없습니다. price-scraper 를 먼저 실행하세요.")
    scraped = load_json(SCRAPED)
    watch = {p["id"]: p for p in load_json(WATCHLIST)["products"]}
    rows = read_rows()

    new_rows, skipped = record(scraped, watch, rows)
    created = append_rows(new_rows) if new_rows else False

    stats = build_stats(rows + new_rows, watch)
    with open(STATS_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"prices.csv {'새로 생성' if created else '기존 파일에 추가'}: {len(new_rows)}행 기록")
    for s in skipped:
        print(f"  - {s}")
    print("\n[상품별 가격 통계]")
    for p in stats["products"]:
        rem = p["remaining_to_target"]
        rem_txt = "-" if rem is None else (f"{won(rem)} 남음" if rem > 0 else "목표 달성")
        trend_txt = p["trend_7d"]
        if p["trend_7d_samples"] >= 2:
            trend_txt += f" ({p['trend_7d_change']:+,}원, {p['trend_7d_samples']}건)"
        else:
            trend_txt += f" (최근 7일 데이터 {p['trend_7d_samples']}건)"
        print(f"- {p['id']} {p['name']} (수집 {p['count']}회, 최근 {won(p['latest'])})")
        print(f"  역대 최저 {won(p['all_time_low'])} | 최고 {won(p['all_time_high'])} | "
              f"평균 {won(p['average'])}")
        print(f"  목표가 {won(p['target']) if p['target'] is not None else '-'} → {rem_txt} | "
              f"7일 추세: {trend_txt}")
    print("\n저장: prices.csv, price_stats.json")


if __name__ == "__main__":
    main()
