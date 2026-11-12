"""telegram-sender: daily_report.md -> 텔레그램 메시지 형식 변환 -> 봇으로 발송

- 텔레그램 값은 같은 폴더의 .env 에서 읽는다 (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- HTTP 호출은 requests 사용
- 4000자 초과 시 이슈 단위로 분할, 실패 시 1회 재시도, 결과는 logs/telegram_log.json 에 기록
실행: python telegram_sender.py   (발송 없이 미리보기: python telegram_sender.py --dry-run)
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = Path(__file__).resolve().parent
SEP = "-" * 63
MAX_LEN = 4000
DISCLAIMER = "본 분석은 참고용이며 투자권유가 아닙니다."
TOKEN_KEYS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN", "BOT_TOKEN")
CHAT_KEYS = ("TELEGRAM_CHAT_ID", "CHAT_ID")


def load_env():
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def first_env(keys):
    for k in keys:
        if os.environ.get(k):
            return os.environ[k]
    return None


def parse_report(text):
    """daily_report.md 에서 날짜, 이슈 목록, 한줄요약을 뽑는다."""
    date_m = re.search(r"날짜\s*:\s*(\d{4}-\d{2}-\d{2})", text)
    report_date = date_m.group(1) if date_m else datetime.now().strftime("%Y-%m-%d")

    issues, cur = [], None
    lines = text.splitlines()
    for line in lines:
        s = line.strip()
        m = re.match(r"\[이슈(\d+)\]\s*(.+)", s)
        if m:
            title = re.sub(r"\([^()]*\)$", "", m.group(2)).strip()  # 끝의 (출처) 제거
            cur = {"no": m.group(1), "title": title, "bull": "", "bear": "", "impact": ""}
            issues.append(cur)
        elif cur and s.startswith("강세예상"):
            cur["bull"] = s.split(":", 1)[1].strip()
        elif cur and s.startswith("약세예상"):
            cur["bear"] = s.split(":", 1)[1].strip()
        elif cur and s.startswith("영향강도"):
            cur["impact"] = s.replace("영향강도", "").strip(" :")

    summary = ""
    for i, line in enumerate(lines):
        if line.strip() == "오늘의 한줄요약" and i + 1 < len(lines):
            summary = lines[i + 1].strip()
            break
    return report_date, issues, summary


def build_blocks(report_date, issues, summary):
    header = f"오늘의 뉴스기반 주식영향분석\n날짜 : {report_date}\n\n{SEP}"
    issue_blocks = [
        f"[이슈{it['no']}]{it['title']}\n강세: {it['bull']}\n약세: {it['bear']}\n영향강도: {it['impact']}"
        for it in issues
    ]
    footer = f"{SEP}\n\n오늘의 한줄요약: {summary}\n{DISCLAIMER}"
    return header, issue_blocks, footer


def split_messages(header, issue_blocks, footer):
    """4000자 이하가 되도록 이슈 단위로 나눈다."""
    msgs, cur = [], header
    for block in issue_blocks + [footer]:
        candidate = f"{cur}\n\n{block}"
        if len(candidate) > MAX_LEN:
            msgs.append(cur)
            cur = block
        else:
            cur = candidate
    msgs.append(cur)
    if len(msgs) > 1:
        msgs = [f"({i}/{len(msgs)})\n{m}" for i, m in enumerate(msgs, 1)]
    return msgs


def send(token, chat_id, text):
    """1회 재시도 포함 발송. (성공여부, message_id, 에러, 재시도여부) 반환"""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    err = None
    for attempt in range(2):
        try:
            r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=15)
            body = r.json()
            if r.ok and body.get("ok"):
                return True, body["result"]["message_id"], None, attempt > 0
            err = f"HTTP {r.status_code}: {body.get('description', r.text[:200])}"
        except (requests.RequestException, ValueError) as e:
            err = f"{type(e).__name__}: {str(e).replace(token, '***')}"
        if attempt == 0:
            print(f"[telegram-sender] 발송 실패 → 3초 후 1회 재시도 ({err})")
            time.sleep(3)
    return False, None, err, True


def write_daily_log(entry):
    """logs/telegram_YYYY-MM-DD.log 에 한 줄씩 추가 (토큰은 기록하지 않음)"""
    logs = BASE / "logs"
    logs.mkdir(exist_ok=True)
    path = logs / f"telegram_{datetime.now().strftime('%Y-%m-%d')}.log"
    lines = [f"[{entry['sent_at']}] report={entry['report_date']} parts={entry['parts']} "
             f"lengths={entry['lengths']} result={'SUCCESS' if entry['success'] else 'FAIL'}"]
    for r in entry["results"]:
        lines.append(f"    part={r.get('part', '-')} ok={r['ok']} message_id={r.get('message_id')} "
                     f"retried={r.get('retried', False)} error={r.get('error')}")
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_log(entry):
    write_daily_log(entry)
    logs = BASE / "logs"
    logs.mkdir(exist_ok=True)
    path = logs / "telegram_log.json"
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        history = []
    history.append(entry)
    path.write_text(json.dumps(history[-200:], ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    dry_run = "--dry-run" in sys.argv

    report_path = BASE / "daily_report.md"
    if not report_path.exists():
        sys.exit("[telegram-sender] daily_report.md 가 없습니다. report-printer 를 먼저 실행하세요.")
    report_date, issues, summary = parse_report(report_path.read_text(encoding="utf-8"))
    messages = split_messages(*build_blocks(report_date, issues, summary))

    for m in messages:
        print(m, "\n")
    print(f"[telegram-sender] 메시지 {len(messages)}개 / 길이 {[len(m) for m in messages]}")
    if dry_run:
        print("[telegram-sender] --dry-run: 발송하지 않음")
        return

    load_env()
    token, chat_id = first_env(TOKEN_KEYS), first_env(CHAT_KEYS)
    results = []
    if not token or not chat_id:
        results.append({"ok": False, "error": "텔레그램 토큰 또는 chat_id 가 설정 파일에 없음"})
    else:
        for i, m in enumerate(messages, 1):
            ok, mid, err, retried = send(token, chat_id, m)
            results.append({"part": i, "ok": ok, "message_id": mid, "error": err, "retried": retried})

    success = bool(results) and all(r["ok"] for r in results)
    lengths = [len(m) for m in messages]
    write_log({"sent_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "report_date": report_date,
               "parts": len(messages), "lengths": lengths, "success": success, "results": results})
    print(f"[telegram-sender] 발송결과: {'성공' if success else '실패'} / 메시지 {len(messages)}개 / "
          f"길이 {', '.join(f'{n}자' for n in lengths)}")
    for r in results:
        if not r["ok"]:
            print(f"[telegram-sender] 실패 사유: {r.get('error')} (logs/telegram_{datetime.now():%Y-%m-%d}.log 기록)")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
