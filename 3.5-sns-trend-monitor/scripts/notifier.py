"""notifier — data/trend_report.html → Gmail(BCC, 구독자 전원), data/telegram_summary.txt → 텔레그램

- 이메일 성공 여부와 무관하게 텔레그램은 항상 발송
- 각각 실패 시 1회 재시도
- 결과 알림: 성공 '트렌드 보고서 발송완료 | 이메일 {N}명 / 텔레그램'
            실패 '발송오류:{오류내용}' (텔레그램이 살아 있으면 오류 알림도 텔레그램으로 전송)

사용: python scripts/notifier.py [--date YYYY-MM-DD] [--dry-run]
"""
import argparse
import json
import os
import re
import smtplib
import sys
import time
from datetime import date
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
TG_LIMIT = 4000


def log(msg):
    print(msg, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / f"notifier_{date.today():%Y%m%d}.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def resolve(value):
    """'${VAR}' 형태면 환경변수(.env)에서 읽는다"""
    m = re.fullmatch(r"\$\{(\w+)\}", str(value or ""))
    return os.getenv(m.group(1), "") if m else value


def with_retry(fn, attempts):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            log(f"  시도 {i + 1}/{attempts} 실패: {e}")
            if i + 1 < attempts:
                time.sleep(3)
    raise last


def send_email(cfg, html, subject):
    ec = cfg["email"]
    user, pw = resolve(ec["gmail_user"]), resolve(ec["gmail_app_password"])
    if not user or not pw:
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD 가 .env에 없음")
    subs = [s for s in cfg.get("subscribers", []) if s]
    if not subs:
        raise RuntimeError("subscribers 비어 있음")

    msg = MIMEText(html, "html", "utf-8")  # Content-Type: text/html; charset=utf-8
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header("SNS 트렌드", "utf-8")), user))
    msg["To"] = user  # 수신자 목록은 BCC로만 (헤더에 노출 안 함)

    def _send():
        with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"], timeout=30) as s:
            s.starttls()
            s.login(user, pw.replace(" ", ""))
            s.sendmail(user, subs, msg.as_string())
    with_retry(_send, ec.get("max_attempts", 2))
    return len(subs)


def send_telegram(cfg, text):
    tc = cfg["telegram"]
    token, chat_id = resolve(tc["bot_token"]), resolve(tc["chat_id"])
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 .env에 없음")
    text = text[:TG_LIMIT]

    def _send():
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                          timeout=20)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if not body.get("ok"):
            # 토큰이 오류 메시지에 섞이지 않도록 description만 사용
            raise RuntimeError(f"HTTP {r.status_code} {body.get('description', '')}".strip())
    with_retry(_send, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true", help="발송 없이 제목·수신자·설정만 점검")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    cfg = json.loads((ROOT / "trend_config.json").read_text(encoding="utf-8"))
    html_path = ROOT / cfg["report"]["html_path"]
    tg_path = ROOT / cfg["report"]["telegram_path"]
    for p in (html_path, tg_path):
        if not p.exists():
            log(f"발송오류:{p.relative_to(ROOT)} 없음 → report-composer를 먼저 실행하세요")
            return 1
    html = html_path.read_text(encoding="utf-8")
    tg_text = tg_path.read_text(encoding="utf-8")

    ec = cfg["email"]
    subject = ec["subject_format"].format(
        date=args.date, topics=ec.get("topics_joiner", "·").join(cfg["topics"]))

    if args.dry_run:
        env_ok = {k: bool(resolve(v)) for k, v in [
            ("GMAIL_ADDRESS", ec["gmail_user"]), ("GMAIL_APP_PASSWORD", ec["gmail_app_password"]),
            ("TELEGRAM_BOT_TOKEN", cfg["telegram"]["bot_token"]), ("TELEGRAM_CHAT_ID", cfg["telegram"]["chat_id"])]}
        log(f"[dry-run] 제목: {subject}")
        log(f"[dry-run] 구독자 {len(cfg['subscribers'])}명, 텔레그램 {len(tg_text)}자, 환경변수 설정 여부: {env_ok}")
        return 0

    errors, email_n, tg_ok = [], 0, False

    if ec.get("enabled", True):
        try:
            email_n = send_email(cfg, html, subject)
            log(f"[이메일] 발송 성공 — {email_n}명 (BCC)")
        except Exception as e:
            errors.append(f"이메일 {e}")
            log(f"[이메일] 발송 실패: {e}")

    # 이메일 결과와 무관하게 텔레그램은 항상 발송
    if cfg["telegram"].get("telegram_alert", True):
        try:
            send_telegram(cfg, tg_text)
            tg_ok = True
            log("[텔레그램] 발송 성공")
        except Exception as e:
            errors.append(f"텔레그램 {e}")
            log(f"[텔레그램] 발송 실패: {e}")

    if not errors:
        log(f"트렌드 보고서 발송완료 | 이메일 {email_n}명 / 텔레그램")
        return 0

    result = "발송오류:" + " / ".join(errors)
    log(result)
    if tg_ok:  # 이메일만 실패한 경우 오류 내용을 텔레그램으로도 알림
        try:
            send_telegram(cfg, result)
        except Exception:
            pass
    return 1


if __name__ == "__main__":
    sys.exit(main())
