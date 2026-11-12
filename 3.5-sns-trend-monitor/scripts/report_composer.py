"""report-composer — data/trend_report_{날짜}.json → data/trend_report.html(이메일) + data/telegram_summary.txt

사용: python scripts/report_composer.py [--date YYYY-MM-DD]
"""
import argparse
import json
import sys
from datetime import date
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CAT_LABEL = {"rising": "급상승", "up": "상승", "down": "하락", "new": "신규", "same": "유지"}
CAT_ROW_BG = {"rising": "#FFF3E0", "new": "#E8F5E9"}
CAT_COLOR = {"rising": "#E65100", "up": "#2E7D32", "down": "#C62828", "new": "#1B5E20", "same": "#757575"}
FONT = "font-family:'Apple SD Gothic Neo','Malgun Gothic','맑은 고딕',Arial,sans-serif;"
TG_LIMIT = 4000


def source_icons(sources):
    """출처 아이콘 — 이메일 클라이언트 호환을 위해 이미지 대신 인라인 스타일 배지"""
    icons = {
        "x": '<span style="display:inline-block;background:#000;color:#fff;font-size:11px;'
             'font-weight:bold;border-radius:3px;padding:1px 5px;margin-right:3px;">𝕏</span>',
        "linkedin": '<span style="display:inline-block;background:#0A66C2;color:#fff;font-size:11px;'
                    'font-weight:bold;border-radius:3px;padding:1px 5px;margin-right:3px;">in</span>',
    }
    return "".join(icons[s] for s in sources if s in icons)


def change_text(item):
    rc = item.get("rank_change")
    if rc is None:
        return "NEW"
    if rc > 0:
        return f"▲{rc}"
    if rc < 0:
        return f"▼{abs(rc)}"
    return "–"


# ---------------- HTML ----------------
def section_rising(report, top_n):
    has_prev = report["has_previous"]
    title = "🔥 이번 주 급상승 키워드 TOP5" if has_prev else "🔥 이번 주 TOP5 키워드"
    note = "" if has_prev else (
        '<p style="margin:0 0 12px;font-size:12px;color:#888;">지난주 데이터가 없어 순위 변화 없이 '
        '이번 주 언급 상위 키워드를 보여줍니다.</p>')
    rows = []
    for t in report["topics"]:
        items = t["rising"][:top_n] if has_prev else t["top_keywords"][:top_n]
        if items:
            cards = "".join(
                f'<td width="20%" valign="top" style="padding:4px;">'
                f'<div style="background:#FFF5F5;background-image:linear-gradient(135deg,#FF6B6B 0%,#FFF5F5 70%);'
                f'border-radius:8px;padding:10px 8px;min-height:92px;">'
                f'<span style="display:inline-block;background:#fff;color:#FF6B6B;font-weight:bold;'
                f'font-size:12px;border-radius:10px;padding:1px 8px;">{i + 1}</span>'
                f'<div style="font-size:14px;font-weight:bold;color:#1A1A2E;margin:8px 0 4px;'
                f'word-break:keep-all;overflow-wrap:break-word;">{escape(it["word"])}</div>'
                f'<div style="font-size:12px;color:#C62828;font-weight:bold;margin-bottom:6px;">'
                f'{"전주 대비 " + change_text(it) if has_prev else str(it["count"]) + "회 언급"}</div>'
                f'{source_icons(it.get("sources", []))}</div></td>'
                for i, it in enumerate(items))
            cards += '<td width="20%"></td>' * (top_n - len(items))
        else:
            cards = (f'<td colspan="{top_n}" style="padding:8px;font-size:13px;color:#888;">'
                     f'이번 주 급상승 키워드 없음</td>')
        rows.append(
            f'<tr><td colspan="{top_n}" style="padding:12px 4px 2px;font-size:14px;font-weight:bold;'
            f'color:#1A1A2E;">{escape(t["topic"])}</td></tr><tr>{cards}</tr>')
    return (f'<h2 style="font-size:18px;color:#1A1A2E;margin:0 0 8px;">{title}</h2>{note}'
            f'<table width="100%" cellpadding="0" cellspacing="0" style="table-layout:fixed;">'
            f'{"".join(rows)}</table>')


def section_table(report):
    th = ('style="background:#1A1A2E;color:#fff;font-size:12px;padding:8px 6px;'
          'text-align:center;font-weight:normal;"')
    td = 'style="padding:7px 6px;font-size:13px;border-bottom:1px solid #eee;text-align:center;"'
    blocks = []
    for t in report["topics"]:
        trs = []
        for it in t["top_keywords"]:
            cat = it.get("category", "new")
            bg = f'background:{CAT_ROW_BG[cat]};' if cat in CAT_ROW_BG else ""
            prev_cnt = it.get("prev_count")
            trs.append(
                f'<tr style="{bg}">'
                f'<td style="padding:7px 6px;font-size:13px;border-bottom:1px solid #eee;text-align:left;">'
                f'{escape(it["word"])}</td>'
                f'<td {td}>{it["count"]}</td>'
                f'<td {td}>{prev_cnt if prev_cnt is not None else "-"}</td>'
                f'<td {td}>{change_text(it)}</td>'
                f'<td style="padding:7px 6px;font-size:12px;border-bottom:1px solid #eee;text-align:center;'
                f'color:{CAT_COLOR[cat]};font-weight:bold;">{CAT_LABEL[cat]}</td></tr>')
        if not trs:
            trs.append(f'<tr><td colspan="5" {td}>수집된 키워드 없음</td></tr>')
        blocks.append(
            f'<h3 style="font-size:15px;color:#1A1A2E;margin:18px 0 6px;">{escape(t["topic"])}</h3>'
            f'<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">'
            f'<tr><th {th} align="left">키워드</th><th {th}>이번주 빈도</th><th {th}>전주 빈도</th>'
            f'<th {th}>변화</th><th {th}>분류</th></tr>{"".join(trs)}</table>')
    return ('<h2 style="font-size:18px;color:#1A1A2E;margin:0 0 4px;">📊 분야별 트렌드 변화표</h2>'
            '<p style="margin:0;font-size:12px;color:#888;">'
            '<span style="background:#FFF3E0;padding:0 6px;">급상승</span> '
            '<span style="background:#E8F5E9;padding:0 6px;">신규</span></p>' + "".join(blocks))


def section_summary(report):
    items = "".join(
        f'<div style="background:#F8F9FA;border-left:4px solid #4A90D9;padding:12px 14px;margin:0 0 10px;">'
        f'<div style="font-size:14px;font-weight:bold;color:#1A1A2E;margin-bottom:4px;">{escape(t["topic"])}</div>'
        f'<div style="font-size:13px;line-height:1.6;color:#333;">{escape(t["summary"])}</div></div>'
        for t in report["topics"])
    overall = report.get("overall_summary")
    if overall:
        items = (f'<div style="background:#F8F9FA;border-left:4px solid #4A90D9;padding:12px 14px;margin:0 0 10px;">'
                 f'<div style="font-size:14px;font-weight:bold;color:#1A1A2E;margin-bottom:4px;">전체 흐름</div>'
                 f'<div style="font-size:13px;line-height:1.6;color:#333;">{escape(overall)}</div></div>') + items
    return f'<h2 style="font-size:18px;color:#1A1A2E;margin:0 0 10px;">🤖 AI 트렌드 분석</h2>{items}'


def build_html(report, cfg):
    d = report["date"]
    topics = " · ".join(t["topic"] for t in report["topics"])
    body_sections = [section_rising(report, cfg["report"]["rising_top_n"]),
                     section_table(report), section_summary(report)]
    sections = "".join(f'<tr><td style="padding:22px 24px 4px;">{s}</td></tr>' for s in body_sections)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SNS 트렌드 위클리 {d}</title></head>
<body style="margin:0;padding:0;background:#EEF0F3;{FONT}">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF0F3;"><tr><td align="center" style="padding:20px 8px;">
<table width="680" cellpadding="0" cellspacing="0" style="max-width:680px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;{FONT}">
<tr><td style="background:#1A1A2E;color:#ffffff;padding:26px 24px;">
<div style="font-size:22px;font-weight:bold;color:#ffffff;">SNS 트렌드 위클리 — {d} 기준</div>
<div style="font-size:13px;color:#C9CCE0;margin-top:6px;">{escape(topics)} | X/LinkedIn</div>
</td></tr>
{sections}
<tr><td style="padding:20px 24px;background:#F1F2F5;font-size:11px;line-height:1.7;color:#888;">
수집 소스: X(x.com) · LinkedIn 공개 게시물 — Tavily 검색 API (X 실패 시 Nitter RSS)<br>
키워드 추출·요약: Claude · 최근 7일 게시물 기준<br>
이 보고서는 sns-trend-monitor가 자동 생성했습니다.
</td></tr>
</table></td></tr></table>
</body></html>
"""


# ---------------- 텔레그램 ----------------
def build_telegram(report, cfg):
    rc = cfg["report"]
    has_prev = report["has_previous"]
    lines = [f"[SNS 트렌드 요약] {report['date']}", "-------------------------------"]
    for t in report["topics"]:
        emoji = rc["topic_emoji"].get(t["topic"], rc["default_emoji"])
        lines.append(f"{emoji} {t['topic']}")
        if has_prev:
            rising = " / ".join(f"{i['word']}(▲{i['rank_change']})" for i in t["rising"][:rc["telegram_rising_n"]])
            lines.append(f"급상승 : {rising or '없음'}")
            new = ", ".join(i["word"] for i in t["new"][:rc["telegram_new_n"]])
        else:
            top = " / ".join(f"{i['word']}({i['count']}회)" for i in t["top_keywords"][:rc["telegram_rising_n"]])
            lines.append(f"급상승 : 첫 수집이라 비교 없음 · TOP {top}")
            new = ", ".join(i["word"] for i in t["top_keywords"][:rc["telegram_new_n"]])
        lines.append(f"신규진입 : {new or '없음'}")
        lines.append(t["summary"].strip())
        lines.append("")
    footer = "전체 보고서는 이메일로 발송됩니다."
    msg = "\n".join(lines) + "\n" + footer
    if len(msg) > TG_LIMIT:  # 4000자 초과 시 본문을 잘라 footer 유지
        msg = "\n".join(lines)[: TG_LIMIT - len(footer) - 4] + "…\n\n" + footer
    return msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    cfg = json.loads((ROOT / "trend_config.json").read_text(encoding="utf-8"))
    src = DATA / f"trend_report_{args.date}.json"
    if not src.exists():
        print(f"[작성] {src.name} 없음 → trend-analyzer를 먼저 실행하세요")
        return 1
    report = json.loads(src.read_text(encoding="utf-8"))

    html_path = ROOT / cfg["report"]["html_path"]
    tg_path = ROOT / cfg["report"]["telegram_path"]
    html_path.write_text(build_html(report, cfg), encoding="utf-8")
    msg = build_telegram(report, cfg)
    tg_path.write_text(msg, encoding="utf-8")
    print(f"[작성] {html_path.relative_to(ROOT)} / {tg_path.relative_to(ROOT)} ({len(msg)}자)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
