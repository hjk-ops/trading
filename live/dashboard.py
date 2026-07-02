"""실시간 매매 모니터링 웹 대시보드.

의존성 없음 (파이썬 표준 라이브러리만 사용).

사용법:
  # 터미널 1: 매매 봇 실행
  python -m live.trader --exchange upbit --symbol KRW-BTC --strategy donchian --paper

  # 터미널 2: 대시보드 실행 후 브라우저에서 http://localhost:8800 접속
  python -m live.dashboard
"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = 8800

PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trading Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, 'Apple SD Gothic Neo', sans-serif;
         background: #0f1117; color: #e6e6e6; margin: 0; padding: 20px; }
  h1 { font-size: 20px; margin: 0 0 16px; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px,1fr));
           gap: 12px; margin-bottom: 20px; }
  .card { background: #1a1d27; border-radius: 12px; padding: 16px; }
  .card .label { font-size: 12px; color: #8b90a0; margin-bottom: 6px; }
  .card .value { font-size: 22px; font-weight: 700; }
  .pos { color: #4ade80; } .neg { color: #f87171; }
  .chart-box { background: #1a1d27; border-radius: 12px; padding: 16px; margin-bottom: 20px; }
  table { width: 100%; border-collapse: collapse; background: #1a1d27;
          border-radius: 12px; overflow: hidden; font-size: 13px; }
  th, td { padding: 10px 12px; text-align: right; }
  th { background: #22263300; color: #8b90a0; font-weight: 600; }
  tr:nth-child(even) { background: #ffffff08; }
  td:first-child, th:first-child { text-align: left; }
  .buy { color: #4ade80; } .sell { color: #f87171; }
  .muted { color: #8b90a0; font-size: 12px; margin-top: 16px; }
</style></head>
<body>
<h1>🤖 자동매매 대시보드 <span id="mode" style="font-size:12px;color:#facc15"></span></h1>
<div class="cards">
  <div class="card"><div class="label">총 자산 (평가)</div><div class="value" id="equity">-</div></div>
  <div class="card"><div class="label">현금</div><div class="value" id="cash">-</div></div>
  <div class="card"><div class="label">보유 수량</div><div class="value" id="qty">-</div></div>
  <div class="card"><div class="label">진입가</div><div class="value" id="entry">-</div></div>
  <div class="card"><div class="label">누적 실현수익</div><div class="value" id="realized">-</div></div>
  <div class="card"><div class="label">거래 횟수 / 승률</div><div class="value" id="stats">-</div></div>
</div>
<div class="chart-box"><canvas id="eqChart" height="90"></canvas></div>
<table>
  <thead><tr><th>시각</th><th>구분</th><th>가격</th><th>금액</th><th>수익률</th></tr></thead>
  <tbody id="trades"></tbody>
</table>
<p class="muted">10초마다 자동 갱신 · 긴급정지: 봇 폴더에서 <code>touch STOP</code></p>
<script>
let chart;
async function refresh() {
  const r = await fetch('/api/status'); const d = await r.json();
  const won = v => v==null ? '-' : Math.round(v).toLocaleString('ko-KR') + '원';
  document.getElementById('cash').textContent = won(d.state.cash);
  document.getElementById('qty').textContent = d.state.qty ? d.state.qty.toFixed(6) : '0';
  document.getElementById('entry').textContent = d.state.entry_price ? won(d.state.entry_price) : '-';
  const eq = d.trades.length ? d.trades[d.trades.length-1].equity : d.state.cash;
  document.getElementById('equity').textContent = won(eq);
  const sells = d.trades.filter(t => t.side === 'SELL' && t.pnl_pct != null);
  const wins = sells.filter(t => t.pnl_pct > 0).length;
  const realized = sells.reduce((a,t) => a + t.pnl_pct, 0);
  const re = document.getElementById('realized');
  re.textContent = realized.toFixed(2) + '%';
  re.className = 'value ' + (realized >= 0 ? 'pos' : 'neg');
  document.getElementById('stats').textContent =
    sells.length ? `${sells.length}회 / ${(wins/sells.length*100).toFixed(0)}%` : '0회 / -';
  document.getElementById('trades').innerHTML = d.trades.slice().reverse().slice(0, 50).map(t =>
    `<tr><td>${t.time}</td><td class="${t.side.toLowerCase()}">${t.side}</td>
     <td>${Math.round(t.price).toLocaleString()}</td><td>${Math.round(t.amount).toLocaleString()}</td>
     <td class="${(t.pnl_pct||0) >= 0 ? 'pos':'neg'}">${t.pnl_pct==null?'-':t.pnl_pct.toFixed(2)+'%'}</td></tr>`
  ).join('');
  const pts = d.trades.filter(t => t.equity != null);
  const cfg = { labels: pts.map(t => t.time.slice(5,16)),
    datasets: [{ label: '총자산', data: pts.map(t => t.equity),
                 borderColor: '#60a5fa', tension: .3, pointRadius: 2, fill: false }] };
  if (!chart) chart = new Chart(document.getElementById('eqChart'),
    { type: 'line', data: cfg, options: { plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: '#8b90a0' } }, y: { ticks: { color: '#8b90a0' } } } } });
  else { chart.data = cfg; chart.update('none'); }
}
refresh(); setInterval(refresh, 10000);
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 콘솔 소음 제거
        pass

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            state = (json.loads(Path("live_state.json").read_text())
                     if Path("live_state.json").exists() else {})
            trades = (json.loads(Path("live_trades.json").read_text())
                      if Path("live_trades.json").exists() else [])
            self._send(json.dumps({"state": state, "trades": trades},
                                  ensure_ascii=False).encode(), "application/json")
        else:
            self._send(PAGE.encode(), "text/html")


if __name__ == "__main__":
    print(f"대시보드 실행: http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
