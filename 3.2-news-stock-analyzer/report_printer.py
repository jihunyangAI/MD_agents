"""report-printer: today_news.json + impact_analysis.json -> 터미널 출력 + daily_report.md

표준 라이브러리만 사용한다. 실행: python report_printer.py
"""
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
LINE = "-" * 46
DISCLAIMER = "본 분석은 참고용이며 투자권유가 아닙니다."
LOG_KEEP_DAYS = 60


def load(name):
    path = BASE / name
    if not path.exists():
        sys.exit(f"[report-printer] {name} 파일이 없습니다. 이전 단계를 먼저 실행하세요.")
    return json.loads(path.read_text(encoding="utf-8"))


def short_name(stock):
    """'SK하이닉스(000660, 코스피)' -> 'SK하이닉스'"""
    return stock.split("(")[0].strip()


def one_line(text):
    """첫 문장만 남긴다."""
    text = text.strip()
    for sep in (". ", "다. "):
        if sep in text:
            head = text.split(sep)[0]
            return head + ("." if sep == ". " else "다.")
    return text


def side_lines(label, side):
    stocks = [short_name(s) for s in side.get("stocks", [])]
    if not stocks:
        return [f"{label} : 뚜렷한 종목 없음 (➖ 중립)", f"  --> 이유 : {one_line(side.get('reason', ''))}"]
    return [f"{label} : {' , '.join(stocks)}", f"  --> 이유 : {one_line(side['reason'])}"]


def default_summary(analysis):
    s = analysis.get("summary", {})
    return (f"강세 {s.get('bullish', 0)}건 / 약세 {s.get('bearish', 0)}건 / "
            f"중립 {s.get('neutral', 0)}건으로 전반적인 흐름을 지켜볼 필요가 있음")


def build_report(news, analysis):
    by_rank = {n["rank"]: n for n in news.get("news", [])}
    lines = [LINE, "오늘의 뉴스기반 주식영향분석", f"날짜 : {news.get('date', date.today().isoformat())}", LINE, ""]

    for i, a in enumerate(analysis.get("analysis", []), start=1):
        n = by_rank.get(a["rank"], {})
        title = n.get("title_ko") or a.get("title_ko", "")
        source = n.get("source", "출처 미상").split(" (")[0]  # 'Reuters (WSJ 보도 인용)' -> 'Reuters'
        lines.append(f"[이슈{i}] {title}({source})")
        lines += side_lines("강세예상", a.get("bullish", {}))
        lines += side_lines("약세예상", a.get("bearish", {}))
        lines.append(f"영향강도 {a.get('impact_level', '보통')}")
        lines.append("")

    summary = analysis.get("market_summary") or default_summary(analysis)
    lines += [LINE, "오늘의 한줄요약", f"  {summary}", LINE, "", DISCLAIMER]
    return "\n".join(lines) + "\n"


def backup_and_prune(report, report_date):
    logs = BASE / "logs"
    logs.mkdir(exist_ok=True)
    (logs / f"report_{report_date}.md").write_text(report, encoding="utf-8")
    cutoff = date.today() - timedelta(days=LOG_KEEP_DAYS)
    for f in logs.glob("report_*.md"):
        try:
            if date.fromisoformat(f.stem.replace("report_", "")) < cutoff:
                f.unlink()
        except ValueError:
            pass


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    news = load("today_news.json")
    analysis = load("impact_analysis.json")
    report = build_report(news, analysis)
    print(report)
    (BASE / "daily_report.md").write_text(report, encoding="utf-8")
    backup_and_prune(report, news.get("date", date.today().isoformat()))
    print("[report-printer] daily_report.md 저장 완료")


if __name__ == "__main__":
    main()
