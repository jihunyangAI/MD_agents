"""텔레그램 알림: value_report.json -> 조건 충족 매물 텔레그램 발송

조건: 최종점수 >= alert_score_threshold AND 가격 <= max_price_억 (value_report.alert_candidates)
중복 방지: 같은 매물 ID는 7일 안에 1번만 보냄 (alert_state.json)
결과는 logs/run_YYYY-MM-DD.md에 기록. 표준 라이브러리만 사용.

  python telegram_alert.py            # 실제 발송
  python telegram_alert.py --dry-run  # 발송 없이 메시지 미리보기 (샘플 1건 포함)
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(BASE, "alert_state.json")
DISCLAIMER = "본 분석은 참고용이며 투자 판단은 본인 책임입니다."
DEDUP_DAYS = 7


def load(name, default=None):
    p = os.path.join(BASE, name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load_env():
    env = {}
    p = os.path.join(BASE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def area_info(name, area):
    return next((a for a in (load(name) or {}).get("areas", []) if a["area"] == area), {})


def naver_link(area, apt):
    dong = area.split()[-1]
    return "https://m.land.naver.com/search/result/" + urllib.parse.quote(f"{dong} {apt}")


def build_message(c):
    area = c["area"]
    tr, sc, po = area_info("transport_score.json", area), area_info("school_score.json", area), area_info("policy_score.json", area)
    disc = c.get("discount_vs_avg_pct")
    if disc is None:
        price_txt = "비교 거래 부족(평균 수준으로 간주)"
    elif disc >= 0:
        price_txt = f"평균가 대비 {disc}% 저렴"
    else:
        price_txt = f"평균가 대비 {abs(disc)}% 비쌈"
    pyeong = c.get("pyeong_supply_est") or round(c["exclusive_m2"] / 3.3058, 1)
    lines = [
        f"[매물알람] 미래가치 {c['total']}점 매물 발견!",
        f"위치: {area} {c['apt']} | 면적 : {pyeong}평 | 가격 : {c['price_억']}억",
        "분석결과 :",
        f"   - 시세대비 : {price_txt}",
        f"   - 교통호재 : {tr.get('summary', '정보 없음')} ({tr.get('score', '-')}/30)",
        f"   - 학군평가 : {sc.get('grade', '정보 없음')} ({sc.get('score', '-')}/20)",
        f"   - 정책현황 : {po.get('summary', '정보 없음')} ({po.get('score', '-')}/20)",
        f"투자의견 : {c['opinion']} (참고용)",
        f"네이버부동산 링크 : {naver_link(area, c['apt'])}",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def send(token, chat_id, text):
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for attempt in range(2):  # 1회 재시도
        try:
            with urllib.request.urlopen(url, data=data, timeout=20) as r:
                return json.loads(r.read()).get("ok", False)
        except Exception:
            if attempt == 1:
                return False
            time.sleep(3)


def write_log(lines):
    os.makedirs(os.path.join(BASE, "logs"), exist_ok=True)
    path = os.path.join(BASE, "logs", f"run_{datetime.now():%Y-%m-%d}.md")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n## telegram-alert {datetime.now():%H:%M:%S}\n" + "\n".join(f"- {l}" for l in lines) + "\n")


def main():
    dry = "--dry-run" in sys.argv
    cfg = load("watch_config.json", {})
    report = load("value_report.json")
    if not report:
        print("value_report.json 없음: value-analyzer를 먼저 실행하세요")
        sys.exit(1)

    threshold = cfg.get("alert_score_threshold", 70)
    max_price = cfg.get("max_price_억", 999)
    cands = [c for c in report.get("alert_candidates", [])
             if c["total"] >= threshold and c["price_억"] <= max_price]

    if dry:
        sample = cands[:1] or [dict(area=a["area"], **a["complexes"][0])
                               for a in report["areas"] if a["complexes"]][:1]
        for c in sample:
            print("----- 미리보기 (발송 안 함) -----")
            print(build_message(c))
        print(f"\n조건 충족 매물 {len(cands)}건 (기준 {threshold}점, {max_price}억 이하)")
        return

    if not cfg.get("telegram_alert", True):
        write_log([f"telegram_alert=false: 발송 안 함 (후보 {len(cands)}건)"])
        print("telegram_alert 꺼짐")
        return

    env = load_env()
    token, chat_id = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    state = load("alert_state.json", {})
    now = datetime.now()
    state = {k: v for k, v in state.items()
             if now - datetime.fromisoformat(v) < timedelta(days=DEDUP_DAYS)}  # 7일 지난 기록 정리

    log, sent, skipped = [], 0, 0
    if not cands:
        log.append(f"알림 조건 미충족: 발송 없음 (기준 {threshold}점 이상, {max_price}억 이하)")
    elif not token or not chat_id:
        log.append("텔레그램 토큰/chat_id가 .env에 없음: 발송 건너뜀")
    for c in cands if token and chat_id else []:
        cid = c["id"]
        if cid in state:
            skipped += 1
            log.append(f"중복 방지(7일 이내 발송됨): {cid}")
            continue
        if send(token, chat_id, build_message(c)):
            state[cid] = now.isoformat(timespec="seconds")
            sent += 1
            log.append(f"발송: {cid} ({c['total']}점, {c['price_억']}억)")
        else:
            log.append(f"발송 실패: {cid}")
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log.append(f"합계: 후보 {len(cands)}건 / 발송 {sent}건 / 중복 생략 {skipped}건")
    write_log(log)
    print("\n".join(log))


if __name__ == "__main__":
    main()
