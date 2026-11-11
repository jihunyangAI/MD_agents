"""price-chart: prices.csv -> price_chart.html (순수 HTML + CSS + JS, 외부 라이브러리 없음).

표준 라이브러리만 사용한다.
실행: python price_chart.py
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
CSV_PATH = BASE / "prices.csv"
OUT = BASE / "price_chart.html"
RECENT_N = 10


def load_rows():
    if not CSV_PATH.exists():
        sys.exit("prices.csv 가 없습니다. price-recorder 를 먼저 실행하세요.")
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build_data(rows):
    products = {}
    for r in rows:
        p = products.setdefault(r["상품ID"], {"id": r["상품ID"], "points": []})
        p["name"] = r["상품명"]
        p["target"] = int(r["목표가격(원)"]) if r["목표가격(원)"] else None
        p["points"].append({"t": r["수집일시"], "price": int(r["수집가격(원)"])})
    out = []
    for p in products.values():
        prices = [pt["price"] for pt in p["points"]]
        latest, low = prices[-1], min(prices)
        target = p["target"]
        out.append({
            **p,
            "latest": latest,
            "latest_at": p["points"][-1]["t"],
            "low": low,
            "low_at": next(pt["t"] for pt in p["points"] if pt["price"] == low),
            "reached": target is not None and latest <= target,
            # 달성율 = 목표가 / 현재가 × 100 (현재가가 목표가 이하이면 100%)
            "rate": None if target is None else round(min(100.0, target / latest * 100), 1),
        })
    recent = sorted(rows, key=lambda r: r["수집일시"], reverse=True)[:RECENT_N]
    recent = [{
        "t": r["수집일시"], "name": r["상품명"], "price": int(r["수집가격(원)"]),
        "change": r["전일대비변동(원)"], "reached": r["목표달성여부"],
        "discount": r["할인정보"], "stock": r["재고상태"],
    } for r in recent]
    return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "products": out, "recent": recent, "total_rows": len(rows)}


HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>가격 추이 차트</title>
<style>
:root {
  color-scheme: light;
  --bg: #f4f3f0; --surface: #fcfcfb; --border: #e3e2de; --grid: #ebeae6;
  --text-1: #0b0b0b; --text-2: #52514e; --text-3: #7a7974;
  --target: #d03b3b; --good: #0ca30c; --good-bg: #e6f5e6; --track-bg: #eceae5;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100;
  --s5: #e87ba4; --s6: #008300; --s7: #6250d6;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #121211; --surface: #1a1a19; --border: #2e2e2b; --grid: #2a2a27;
    --text-1: #f0efec; --text-2: #c3c2b7; --text-3: #8f8e86;
    --target: #e66767; --good: #0ca30c; --good-bg: #16301a; --track-bg: #2e2e2b;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500;
    --s5: #d55181; --s6: #008300; --s7: #9085e9;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #121211; --surface: #1a1a19; --border: #2e2e2b; --grid: #2a2a27;
  --text-1: #f0efec; --text-2: #c3c2b7; --text-3: #8f8e86;
  --target: #e66767; --good: #0ca30c; --good-bg: #16301a; --track-bg: #2e2e2b;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500;
  --s5: #d55181; --s6: #008300; --s7: #9085e9;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text-1);
  font-family: "Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", system-ui, sans-serif;
  font-size: 14px; line-height: 1.5; }
.wrap { max-width: 1080px; margin: 0 auto; padding: 24px 16px 48px; }
header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 20px; }
h1 { font-size: 22px; margin: 0; }
h2 { font-size: 16px; margin: 32px 0 12px; }
.meta { color: var(--text-3); font-size: 13px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 12px; }
.card-title { display: flex; align-items: center; gap: 8px; font-weight: 600; min-width: 0; }
.card-title span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.swatch { width: 10px; height: 10px; border-radius: 50%; flex: none; }
.badge { flex: none; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-2); }
.badge.ok { background: var(--good-bg); color: var(--text-1); border-color: var(--good); }
.badge.ok::before { content: "✓ "; color: var(--good); }
.badge.track::before { content: "● "; color: var(--text-3); }
.kv { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }
.kv dt { color: var(--text-3); font-size: 12px; }
.kv dd { margin: 0; font-weight: 600; font-variant-numeric: tabular-nums; }
.kv dd.big { font-size: 20px; }
.bar { height: 6px; background: var(--track-bg); border-radius: 3px; margin-top: 12px; overflow: hidden; }
.bar > i { display: block; height: 100%; border-radius: 3px; }
.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 480px), 1fr)); gap: 12px; }
.chart { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; position: relative; }
.chart h3 { font-size: 14px; margin: 0 0 4px; display: flex; align-items: center; gap: 8px; }
.legend { display: flex; flex-wrap: wrap; gap: 14px; color: var(--text-2); font-size: 12px; margin-bottom: 8px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend svg { overflow: visible; }
svg.plot { width: 100%; height: auto; display: block; overflow: visible; }
.axis text { fill: var(--text-3); font-size: 11px; font-variant-numeric: tabular-nums; }
.tip { position: absolute; pointer-events: none; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 16px rgba(0,0,0,.12);
  white-space: nowrap; opacity: 0; transition: opacity .1s; z-index: 2; }
.tip b { font-variant-numeric: tabular-nums; }
.note { color: var(--text-3); font-size: 12px; margin-top: 6px; }
.table-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { color: var(--text-3); font-weight: 600; font-size: 12px; }
tr:last-child td { border-bottom: none; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
th.num { text-align: right; }
.down { color: var(--s1); } .up { color: var(--target); }
.yn-y { color: var(--good); font-weight: 600; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>가격 추이 차트</h1>
    <div class="meta" id="meta"></div>
  </header>

  <h2>현재 상태</h2>
  <div class="cards" id="cards"></div>

  <h2>상품별 가격 변동</h2>
  <div class="charts" id="charts"></div>

  <h2>최근 가격 변동 내역 <span class="meta">(최신 10건)</span></h2>
  <div class="table-wrap"><table>
    <thead><tr><th>수집일시</th><th>상품명</th><th class="num">수집가격</th><th class="num">전일대비</th><th>목표달성</th><th>할인정보</th><th>재고</th></tr></thead>
    <tbody id="recent"></tbody>
  </table></div>
</div>

<script>
const DATA = __DATA__;
const won = n => n == null ? "-" : n.toLocaleString("ko-KR") + "원";
const color = i => `var(--s${(i % 7) + 1})`;
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, parent) => {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
};

document.getElementById("meta").textContent =
  `생성 ${DATA.generated_at} · 누적 ${DATA.total_rows}건 · 상품 ${DATA.products.length}개`;

/* 1) 요약 카드 */
document.getElementById("cards").innerHTML = DATA.products.map((p, i) => `
  <div class="card">
    <div class="card-head">
      <div class="card-title"><i class="swatch" style="background:${color(i)}"></i><span>${esc(p.name)}</span></div>
      <span class="badge ${p.reached ? "ok" : "track"}">${p.reached ? "달성" : "추적 중"}</span>
    </div>
    <dl class="kv">
      <div><dt>현재가</dt><dd class="big">${won(p.latest)}</dd></div>
      <div><dt>목표가</dt><dd class="big">${won(p.target)}</dd></div>
      <div><dt>달성율</dt><dd>${p.rate == null ? "-" : p.rate + "%"}</dd></div>
      <div><dt>역대 최저가</dt><dd>${won(p.low)}</dd></div>
    </dl>
    <div class="bar" title="달성율 ${p.rate}%"><i style="width:${p.rate || 0}%;background:${p.reached ? "var(--good)" : color(i)}"></i></div>
  </div>`).join("");

/* 2) 상품별 선 그래프 (SVG) */
const W = 520, H = 260, M = { t: 16, r: 16, b: 32, l: 72 };
function niceTicks(lo, hi, n = 4) {
  const span = hi - lo || Math.abs(hi) || 1;
  const raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(s => s * mag).find(s => s >= raw);
  const t0 = Math.floor(lo / step) * step, out = [];
  for (let v = t0; v <= hi + step * 0.001; v += step) out.push(v);
  if (out[out.length - 1] < hi) out.push(out[out.length - 1] + step);
  return out;
}
const shortWon = v => v >= 10000 ? (v / 10000).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) + "만" : v.toLocaleString("ko-KR");
const parseT = s => new Date(s.replace(" ", "T") + ":00");
const fmtDate = d => `${d.getMonth() + 1}/${d.getDate()}`;

DATA.products.forEach((p, i) => {
  const box = document.createElement("div");
  box.className = "chart";
  box.innerHTML = `
    <h3><i class="swatch" style="background:${color(i)}"></i>${esc(p.name)}</h3>
    <div class="legend">
      <span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="${color(i)}" stroke-width="2"/></svg>수집가격</span>
      ${p.target != null ? `<span><svg width="22" height="8"><line x1="0" y1="4" x2="22" y2="4" stroke="var(--target)" stroke-width="2" stroke-dasharray="5 4"/></svg>목표가 ${won(p.target)}</span>` : ""}
      <span><svg width="12" height="12" viewBox="-6 -6 12 12"><path d="${star(0, 0, 6)}" fill="${color(i)}" stroke="var(--surface)" stroke-width="1.5"/></svg>역대 최저가</span>
    </div>`;
  const svg = el("svg", { class: "plot", viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `${p.name} 가격 추이 선 그래프` });
  box.appendChild(svg);
  const tip = document.createElement("div"); tip.className = "tip"; box.appendChild(tip);
  if (p.points.length < 2) {
    const n = document.createElement("div"); n.className = "note";
    n.textContent = "수집 데이터가 1건이라 선 대신 점으로 표시합니다. 수집이 쌓이면 추이선이 그려집니다.";
    box.appendChild(n);
  }
  document.getElementById("charts").appendChild(box);

  const pts = p.points.map(d => ({ ...d, d: parseT(d.t) }));
  const vals = pts.map(d => d.price).concat(p.target != null ? [p.target] : []);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.15 || hi * 0.05;
  const ticks = niceTicks(lo - pad, hi + pad);
  lo = ticks[0]; hi = ticks[ticks.length - 1];
  let t0 = pts[0].d.getTime(), t1 = pts[pts.length - 1].d.getTime();
  if (t0 === t1) { t0 -= 86400000; t1 += 86400000; }
  const x = t => M.l + (t - t0) / (t1 - t0) * (W - M.l - M.r);
  const y = v => M.t + (hi - v) / (hi - lo) * (H - M.t - M.b);

  const axis = el("g", { class: "axis" }, svg);
  ticks.forEach(v => {
    el("line", { x1: M.l, x2: W - M.r, y1: y(v), y2: y(v), stroke: "var(--grid)", "stroke-width": 1 }, axis);
    const tx = el("text", { x: M.l - 8, y: y(v) + 4, "text-anchor": "end" }, axis);
    tx.textContent = shortWon(v) + "원";
  });
  // x축: 날짜 라벨 (겹치지 않게 최대 6개)
  const days = [...new Map(pts.map(d => [d.d.toDateString(), d.d])).values()];
  const stepX = Math.max(1, Math.ceil(days.length / 6));
  const xDays = pts.length < 2 ? [pts[0].d] : days.filter((_, k) => k % stepX === 0);
  xDays.forEach(d => {
    const tx = el("text", { x: x(d.getTime()), y: H - M.b + 18, "text-anchor": "middle" }, axis);
    tx.textContent = fmtDate(d);
  });
  el("line", { x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b, stroke: "var(--border)" }, axis);

  if (p.target != null) {
    el("line", { x1: M.l, x2: W - M.r, y1: y(p.target), y2: y(p.target),
      stroke: "var(--target)", "stroke-width": 2, "stroke-dasharray": "6 5" }, svg);
  }
  if (pts.length > 1) {
    el("path", { d: pts.map((d, k) => `${k ? "L" : "M"}${x(d.d.getTime())},${y(d.price)}`).join(""),
      fill: "none", stroke: color(i), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
  }
  pts.forEach(d => {
    if (d.price === p.low && d.t === p.low_at) return;
    el("circle", { cx: x(d.d.getTime()), cy: y(d.price), r: 4, fill: color(i),
      stroke: "var(--surface)", "stroke-width": 2 }, svg);
  });
  const lowPt = pts.find(d => d.t === p.low_at);
  const sx = x(lowPt.d.getTime()), sy = y(lowPt.price);
  el("path", { d: star(sx, sy, 9), fill: color(i), stroke: "var(--surface)", "stroke-width": 2 }, svg);
  const lbl = el("text", { x: sx, y: sy + 22, "text-anchor": "middle", fill: "var(--text-2)",
    "font-size": 11, "font-weight": 600 }, svg);
  lbl.textContent = "최저 " + won(lowPt.price);

  // hover: 크로스헤어 + 툴팁 (가장 가까운 수집 시점)
  const cross = el("line", { y1: M.t, y2: H - M.b, stroke: "var(--text-3)", "stroke-width": 1,
    "stroke-dasharray": "2 3", opacity: 0 }, svg);
  const dot = el("circle", { r: 5, fill: color(i), stroke: "var(--surface)", "stroke-width": 2, opacity: 0 }, svg);
  const hit = el("rect", { x: M.l, y: M.t, width: W - M.l - M.r, height: H - M.t - M.b, fill: "transparent" }, svg);
  const move = ev => {
    const r = svg.getBoundingClientRect(), sc = W / r.width;
    const mx = (ev.clientX - r.left) * sc;
    const near = pts.reduce((a, b) => Math.abs(x(b.d.getTime()) - mx) < Math.abs(x(a.d.getTime()) - mx) ? b : a);
    const px = x(near.d.getTime()), py = y(near.price);
    cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("opacity", 1);
    dot.setAttribute("cx", px); dot.setAttribute("cy", py); dot.setAttribute("opacity", 1);
    const gap = p.target != null ? near.price - p.target : null;
    tip.innerHTML = `${esc(near.t)}<br>수집가격 <b>${won(near.price)}</b>` +
      (gap != null ? `<br>목표가 대비 <b>${gap <= 0 ? "달성" : "+" + won(gap)}</b>` : "");
    const bx = box.getBoundingClientRect();
    let left = r.left - bx.left + px / sc + 12;
    if (left + 180 > bx.width) left -= 200;
    tip.style.left = left + "px"; tip.style.top = (r.top - bx.top + py / sc - 20) + "px";
    tip.style.opacity = 1;
  };
  hit.addEventListener("pointermove", move);
  hit.addEventListener("pointerleave", () => { tip.style.opacity = 0; cross.setAttribute("opacity", 0); dot.setAttribute("opacity", 0); });
});

function star(cx, cy, R) {
  const r = R * 0.45, pts = [];
  for (let k = 0; k < 10; k++) {
    const a = -Math.PI / 2 + k * Math.PI / 5, rr = k % 2 ? r : R;
    pts.push(`${(cx + rr * Math.cos(a)).toFixed(2)},${(cy + rr * Math.sin(a)).toFixed(2)}`);
  }
  return "M" + pts.join("L") + "Z";
}

/* 3) 최근 변동 내역 */
document.getElementById("recent").innerHTML = DATA.recent.map(r => {
  const c = r.change, cls = c.startsWith("-") && c !== "-" ? "down" : c.startsWith("+") ? "up" : "";
  const ctext = c === "-" || c === "0" ? c : (c.startsWith("-") ? "▼ " : "▲ ") + Math.abs(parseInt(c, 10)).toLocaleString("ko-KR") + "원";
  return `<tr><td>${esc(r.t)}</td><td>${esc(r.name)}</td><td class="num">${won(r.price)}</td>
    <td class="num ${cls}">${ctext}</td><td class="${r.reached === "Y" ? "yn-y" : ""}">${r.reached === "Y" ? "✓ Y" : "N"}</td>
    <td>${esc(r.discount)}</td><td>${esc(r.stock)}</td></tr>`;
}).join("") || `<tr><td colspan="7">기록이 없습니다.</td></tr>`;
</script>
</body>
</html>
"""


def main():
    data = build_data(load_rows())
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.write_text(HTML.replace("__DATA__", payload), encoding="utf-8")
    print(f"생성: {OUT.name} (상품 {len(data['products'])}개, 누적 {data['total_rows']}건)")
    for p in data["products"]:
        print(f"- {p['id']} {p['name']}: 현재 {p['latest']:,}원 / 목표 "
              f"{p['target']:,}원 / 달성율 {p['rate']}% / 최저 {p['low']:,}원 / "
              f"{'달성' if p['reached'] else '추적 중'}")


if __name__ == "__main__":
    main()
