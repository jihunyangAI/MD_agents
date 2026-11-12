"""rate-alert: 환율 이력을 분석해 목표가 도달/급변 시 텔레그램으로 알린다."""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
STATE_PATH = BASE_DIR / "alert_state.json"
LOG_DIR = BASE_DIR / "logs"
LOG_KEEP_DAYS = 90
DEDUP_HOURS = 24

# targets.currency → exchange_history.json 키
KEY_MAP = {"KRW": "usd", "JPY": "jpy100", "EUR": "eur"}


def load_env():
    env = {}
    path = BASE_DIR / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def change_info(cur, prev):
    if prev is None:
        return None
    diff = cur - prev
    pct = diff / prev * 100
    arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "-")
    return {"arrow": arrow, "diff": abs(diff), "pct": pct}


def fmt_change(ch):
    if ch is None:
        return "전일 데이터 없음"
    return f"{ch['arrow']} {ch['diff']:,.1f}원 ({ch['pct']:+.2f}%)"


def analyze(config, today, yesterday):
    hits_target, hits_change = [], []
    pct_limit = float(config.get("change_alert_pct", 1.0))
    for t in config["targets"]:
        key = KEY_MAP.get(t["currency"])
        if not key or key not in today:
            continue
        cur = today[key]
        prev = yesterday.get(key) if yesterday else None
        ch = change_info(cur, prev)
        # 조건 1: 목표가 도달
        if cur <= t["alert_below"]:
            hits_target.append({"t": t, "cur": cur, "ref": t["alert_below"], "tip": t["tip_below"], "ch": ch})
        elif cur >= t["alert_above"]:
            hits_target.append({"t": t, "cur": cur, "ref": t["alert_above"], "tip": t["tip_above"], "ch": ch})
        # 조건 2: 급변 감지 (어제 데이터 없으면 건너뜀)
        if ch is not None and abs(ch["pct"]) >= pct_limit:
            hits_change.append({"t": t, "cur": cur, "ch": ch})
    return hits_target, hits_change


def filter_dedup(hits_target, hits_change, state, now):
    """동일 통화·동일 조건은 24시간 내 1회만."""
    def ok(kind, cur):
        last = state.get(f"{kind}:{cur}")
        return not last or now - datetime.fromisoformat(last) >= timedelta(hours=DEDUP_HOURS)
    ht = [h for h in hits_target if ok("target", h["t"]["currency"])]
    hc = [h for h in hits_change if ok("change", h["t"]["currency"])]
    return ht, hc


def build_message(date, today, hits_target, hits_change):
    lines = [f"[환율알림] {date}", ""]
    for h in hits_target:
        lines += [
            f"{h['t']['display']} 목표가 도달!",
            f"현재 : {h['cur']:,.1f}원 (목표기준 : {h['ref']:,}원)",
            f"전일대비 : {fmt_change(h['ch'])} --> {h['tip']}",
            "",
        ]
    for h in hits_change:
        lines += [
            f"{h['t']['display']} 급변감지! 현재 : {h['cur']:,.1f}원 전일대비 : {fmt_change(h['ch'])}",
            "",
        ]
    lines += [
        "오늘전체 환율",
        f"- USD/KRW : {today['usd']:,.1f}원",
        f"- JPY/KRW : {today['jpy100']:,.1f}원 (100엔기준)",
        f"- EUR/KRW : {today['eur']:,.1f}원",
    ]
    return "\n".join(lines)


def log_telegram(line):
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"telegram_{datetime.now(KST).strftime('%Y-%m-%d')}.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} {line}\n")


def send_telegram(token, chat_id, text):
    if not token or not chat_id:
        print(f"[텔레그램] 실패 - .env에 토큰/chat_id 없음 (메시지 길이 {len(text)}자)")
        log_telegram(f"FAIL no-credentials len={len(text)}")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
    for attempt in range(2):
        err = ""
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=15) as resp:
                if json.loads(resp.read().decode("utf-8")).get("ok"):
                    print(f"[텔레그램] 성공 (메시지 길이 {len(text)}자, 시도 {attempt + 1}회)")
                    log_telegram(f"OK len={len(text)} attempt={attempt + 1}")
                    return True
                err = "ok=false"
        except Exception as e:
            err = type(e).__name__
        print(f"[텔레그램] 실패 {attempt + 1}/2 - {err} (메시지 길이 {len(text)}자)")
        log_telegram(f"FAIL attempt={attempt + 1} err={err} len={len(text)}")
        if attempt == 0:
            time.sleep(3)
    return False


def write_log(date, today, yesterday, hits_target, hits_change, sent, skipped_dup, message):
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"exchange_{date}.md"
    now = datetime.now(KST).strftime("%H:%M:%S")
    lines = [
        f"## {now} 알림 분석",
        f"- 오늘: USD {today['usd']} / JPY100 {today['jpy100']} / EUR {today['eur']}",
        f"- 어제: {'없음 (급변 검사 생략)' if not yesterday else yesterday['date']}",
        f"- 목표가 도달: {', '.join(h['t']['display'] for h in hits_target) or '없음'}",
        f"- 급변 감지: {', '.join(h['t']['display'] for h in hits_change) or '없음'}",
    ]
    if skipped_dup:
        lines.append(f"- 24시간 내 중복으로 생략: {', '.join(skipped_dup)}")
    if message is None:
        lines.append("- 결과: 조건 미충족 (발송 안 함)")
    else:
        lines.append(f"- 결과: {'발송 성공' if sent else '발송 실패'}")
        lines += ["", "```", message, "```"]
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")
    # 90일 지난 로그 삭제
    cutoff = (datetime.now(KST) - timedelta(days=LOG_KEEP_DAYS)).strftime("%Y-%m-%d")
    for p in LOG_DIR.glob("exchange_*.md"):
        if p.stem.replace("exchange_", "") < cutoff:
            p.unlink()


def main():
    config = load_json(BASE_DIR / "exchange_config.json", {})
    history = load_json(BASE_DIR / config.get("data_file", "exchange_history.json"), [])
    now = datetime.now(KST)
    date = now.strftime("%Y-%m-%d")
    yday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today = next((h for h in history if h["date"] == date), None)
    yesterday = next((h for h in history if h["date"] == yday), None)
    if today is None:
        print("오늘 수집 데이터가 없습니다. rate_collector.py를 먼저 실행하세요.")
        return

    env = load_env()
    tg = config.get("telegram", {})
    token = env.get(tg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
    chat_id = env.get(tg.get("chat_id_env", "TELEGRAM_CHAT_ID"))

    all_target, all_change = analyze(config, today, yesterday)
    state = load_json(STATE_PATH, {})
    if "--force" in sys.argv:  # 수동 검증용: 24시간 중복 방지 무시
        hits_target, hits_change = all_target, all_change
    else:
        hits_target, hits_change = filter_dedup(all_target, all_change, state, now)
    skipped = [h["t"]["display"] for h in all_target + all_change if h not in hits_target + hits_change]

    if not hits_target and not hits_change:
        write_log(date, today, yesterday, all_target, all_change, False, skipped, None)
        if skipped:
            print(f"알림 대상 있음, 24시간 내 이미 발송해 생략: {', '.join(skipped)}")
        else:
            print("조건 미충족 — 발송하지 않음")
        return

    message = build_message(date, today, hits_target, hits_change)
    sent = send_telegram(token, chat_id, message)
    if sent:
        for h in hits_target:
            state[f"target:{h['t']['currency']}"] = now.isoformat()
        for h in hits_change:
            state[f"change:{h['t']['currency']}"] = now.isoformat()
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    write_log(date, today, yesterday, hits_target, hits_change, sent, skipped, message)
    print(message)
    print(f"\n발송 {'성공' if sent else '실패'}: 목표가 {len(hits_target)}건, 급변 {len(hits_change)}건")


if __name__ == "__main__":
    main()
