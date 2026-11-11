"""price-alert: price_stats.json 을 읽어 목표가 달성 / 10% 이상 하락 시 텔레그램 알림.

표준 라이브러리(urllib)만 사용한다.
  python price_alert.py            # 조건 충족 시 실제 발송
  python price_alert.py --dry-run  # 발송 없이 메시지 미리보기 (.env를 읽지 않음)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATS = BASE / "price_stats.json"
SCRAPED = BASE / "scraped_prices.json"
WATCHLIST = BASE / "watchlist.json"
HISTORY = BASE / "alert_history.json"
ENV_FILE = BASE / ".env"

DROP_THRESHOLD = 0.10  # 직전 수집가 대비 10% 이상 하락
RETRY = 1              # 발송 실패 시 재시도 횟수


def load_json(path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_dotenv(path):
    """.env 의 KEY=VALUE 를 환경변수로 등록 (이미 있는 값은 덮어쓰지 않음)."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def won(n):
    return f"{n:,}원"


def product_url(pid, name, scraped, watch):
    """구매링크: 이번 수집 출처 URL → watchlist url → 다나와 검색 링크 순."""
    for r in (scraped or {}).get("results", []):
        if r.get("id") == pid and r.get("source_url"):
            return r["source_url"]
    if watch.get(pid, {}).get("url"):
        return watch[pid]["url"]
    return "https://search.danawa.com/dsearch.php?query=" + urllib.parse.quote(name)


def build_alerts(stats, scraped, watch):
    alerts = []
    for p in stats.get("products", []):
        name, price, target = p["name"], p["latest"], p.get("target")
        url = product_url(p["id"], name, scraped, watch)
        if target is not None and price <= target:
            saving = target - price
            text = (
                f"[최저가알림] {name} 목표가달성!\n\n"
                f"- 현재가격 : {won(price)}\n"
                f"- 목표가격 : {won(target)}\n"
                f"- 절약금액 : {won(saving)}\n"
                f"- 구매링크 : {url}\n"
                f"- 수집시각 : {p['latest_at']}\n\n"
                f"지금 구매하면 {won(saving)} 절약!"
            )
            alerts.append({"type": "target_reached", "product": p, "url": url, "text": text})
            continue
        prev = p.get("previous")
        if prev and (prev - price) / prev >= DROP_THRESHOLD:
            drop = prev - price
            text = (
                f"[가격하락] {name} 가격이 내렸어요.\n\n"
                f"- 전일대비 하락폭 : -{won(drop)} ({drop / prev:.1%}↓, 직전 {won(prev)})\n"
                f"- 현재가격 : {won(price)}\n"
                f"- 구매링크 : {url}"
            )
            alerts.append({"type": "price_drop", "product": p, "url": url, "text": text})
    return alerts


def send_telegram(token, chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text, "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    last_err = None
    for attempt in range(RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                body = json.loads(res.read().decode("utf-8"))
            if body.get("ok"):
                return True, body["result"]["message_id"], None, attempt
            last_err = body.get("description", "unknown error")
        except urllib.error.HTTPError as e:
            try:
                last_err = f"HTTP {e.code}: {json.loads(e.read().decode()).get('description')}"
            except Exception:
                last_err = f"HTTP {e.code}"
        except Exception as e:  # 네트워크 오류 등 (토큰이 담긴 URL은 기록하지 않음)
            last_err = type(e).__name__ + ": " + str(getattr(e, "reason", "") or e).replace(token, "***")
        if attempt < RETRY:
            time.sleep(2)
    return False, None, last_err, RETRY


def append_history(entries):
    hist = load_json(HISTORY, {"alerts": []})
    hist["alerts"].extend(entries)
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)


def main():
    dry = "--dry-run" in sys.argv
    stats = load_json(STATS)
    if not stats:
        sys.exit("price_stats.json 이 없습니다. price-recorder 를 먼저 실행하세요.")
    scraped = load_json(SCRAPED, {})
    watch = {p["id"]: p for p in load_json(WATCHLIST, {"products": []})["products"]}

    alerts = build_alerts(stats, scraped, watch)
    print(f"알림 조건 충족: {len(alerts)}건 (점검 상품 {len(stats.get('products', []))}개)")
    if not alerts:
        return
    if dry:
        for a in alerts:
            print("\n----- 미리보기 -----\n" + a["text"])
        print("\n(--dry-run: 발송·기록하지 않음)")
        return

    load_dotenv(ENV_FILE)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    entries, sent = [], 0
    for a in alerts:
        p = a["product"]
        if not token or not chat_id:
            ok, mid, err, retries = False, None, "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 가 .env 에 없음", 0
        else:
            ok, mid, err, retries = send_telegram(token, chat_id, a["text"])
        sent += ok
        entries.append({
            "sent_at": now,
            "type": a["type"],
            "product_id": p["id"],
            "product_name": p["name"],
            "price": p["latest"],
            "target": p.get("target"),
            "previous": p.get("previous"),
            "collected_at": p["latest_at"],
            "url": a["url"],
            "success": bool(ok),
            "telegram_message_id": mid,
            "retries": retries,
            "error": err,
        })
        print(f"- {p['id']} {p['name']} [{a['type']}] → {'발송 성공' if ok else '발송 실패: ' + str(err)}")
    append_history(entries)
    print(f"\n알림: {sent}/{len(alerts)}건 발송 · 기록: alert_history.json")


if __name__ == "__main__":
    main()
