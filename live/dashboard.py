"""실시간 매매 모니터링 + 제어 웹 대시보드 v2.

기능: 가격 차트에 진입/청산 마커, 봇 일시정지/재개, 수동 청산, 상태 표시.
제어 버튼은 DASHBOARD_PASSWORD 환경변수(기본 "1234")로 보호된다.

로컬 사용법:
  python -m live.dashboard   # http://localhost:8800
"""
import hmac
import json
import os
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
         background: #0f1117; color: #e6e6e6; margin: 0; padding: 16px; }
  h1 { font-size: 19px; margin: 0 0 4px; display:flex; align-items:center; gap:8px; }
  .sub { font-size: 12px; color: #8b90a0; margin-bottom: 14px; }
  .badge { font-size: 11px; padding: 3px 10px; border-radius: 999px; font-weight: 700; }
  .run { background: #14532d; color: #4ade80; }
  .pause { background: #57320a; color: #fbbf24; }
  .err { background: #5c1a1a; color: #f87171; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr));
           gap: 10px; margin-bottom: 14px; }
  .card { background: #1a1d27; border-radius: 12px; padding: 13px 15px; }
  .card .label { font-size: 11px; color: #8b90a0; margin-bottom: 5px; }
  .card .value { font-size: 19px; font-weight: 700; }
  .pos { color: #4ade80; } .neg { color: #f87171; } .flat { color: #8b90a0; }
  .controls { display:flex; gap:8px; margin-bottom:14px; flex-wrap:wrap; }
  button { border:0; border-radius:10px; padding:11px 16px; font-size:14px;
           font-weight:700; cursor:pointer; }
  .btn-pause { background:#7c2d12; color:#fdba74; }
  .btn-resume { background:#14532d; color:#86efac; }
  .btn-close { background:#374151; color:#e5e7eb; }
  .chart-box { background: #1a1d27; border-radius: 12px; padding: 14px; margin-bottom: 14px; }
  .chart-title { font-size:12px; color:#8b90a0; margin-bottom:8px; }
  table { width: 100%; border-collapse: collapse; background: #1a1d27;
          border-radius: 12px; overflow: hidden; font-size: 12.5px; }
  th, td { padding: 9px 10px; text-align: right; }
  th { color: #8b90a0; font-weight: 600; }
  tr:nth-child(even) { background: #ffffff08; }
  td:first-child, th:first-child { text-align: left; }
  .buy,.long { color: #4ade80; } .sell,.short,.close-l,.close-s { color: #f87171; }
  .muted { color: #8b90a0; font-size: 11.5px; margin-top: 14px; }
</style></head>
<body>
<h1>🤖 자동매매 대시보드 <span id="modebadge" class="badge pause">…</span><span id="badge" class="badge">…</span></h1>
<div class="sub" id="botinfo">상태 불러오는 중…</div>
<div class="controls">
  <button id="toggleBtn" class="btn-pause" onclick="control()">⏸ 일시정지</button>
  <button class="btn-close" onclick="control('close')">✕ 수동 청산</button>
</div>
<div class="cards">
  <div class="card"><div class="label">현재 포지션</div><div class="value" id="position">-</div></div>
  <div class="card"><div class="label">현재가 / 시그널</div><div class="value" id="pricesig">-</div></div>
  <div class="card"><div class="label">잔고 (USDT)</div><div class="value" id="cash">-</div></div>
  <div class="card"><div class="label">누적 실현수익</div><div class="value" id="realized">-</div></div>
  <div class="card"><div class="label">거래 / 승률</div><div class="value" id="stats">-</div></div>
  <div class="card"><div class="label">마지막 체크</div><div class="value" id="lastcheck" style="font-size:14px">-</div></div>
</div>
<div class="chart-box">
  <div class="chart-title">가격 & 매매 지점 (▲ 롱진입 · ▼ 숏진입 · ● 청산)</div>
  <canvas id="pxChart" height="120"></canvas>
</div>
<table>
  <thead><tr><th>시각</th><th>구분</th><th>가격</th><th>금액</th><th>수익률</th></tr></thead>
  <tbody id="trades"></tbody>
</table>
<p class="muted">10초마다 자동 갱신 · 제어 버튼은 비밀번호 필요</p>
<script>
let chart, paused=false;

function pw() {
  let p = sessionStorage.getItem('pw');
  if (!p) { p = prompt('제어 비밀번호'); if (p) sessionStorage.setItem('pw', p); }
  return p;
}
async function control(action) {
  const a = action || (paused ? 'resume' : 'pause');
  const p = pw(); if (!p) return;
  const r = await fetch('/api/control', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action:a, password:p}) });
  if (r.status === 403) { sessionStorage.removeItem('pw'); alert('비밀번호가 틀렸습니다'); return; }
  const d = await r.json(); alert(d.message); refresh();
}
function nearestIdx(labels, t) {
  // 거래시각 "YYYY-MM-DD HH:MM:SS" → 라벨 "MM-DD HH:MM" 근접 탐색
  const key = t.slice(5,16).replace('T',' ');
  let best=-1;
  for (let i=0;i<labels.length;i++) if (labels[i] <= key) best=i;
  return best;
}
async function refresh() {
  const r = await fetch('/api/status'); const d = await r.json();
  const bs = d.bot || {};
  paused = !!bs.paused;
  const badge = document.getElementById('badge');
  if (bs.error) { badge.textContent='오류'; badge.className='badge err'; }
  else if (paused) { badge.textContent='일시정지'; badge.className='badge pause'; }
  else { badge.textContent='가동중'; badge.className='badge run'; }
  const mb = document.getElementById('modebadge');
  if (bs.mode === 'LIVE') { mb.textContent = '실계좌'; mb.className = 'badge err'; }
  else { mb.textContent = '모의'; mb.className = 'badge pause'; }
  document.getElementById('toggleBtn').textContent = paused ? '▶ 재개' : '⏸ 일시정지';
  document.getElementById('toggleBtn').className = paused ? 'btn-resume' : 'btn-pause';
  document.getElementById('botinfo').textContent =
    `${bs.strategy||''} · ${bs.symbol||''} · ${bs.interval||''}` +
    (bs.entry ? ` · 진입가 $${Math.round(bs.entry).toLocaleString()}` : '') +
    (bs.error ? ` · ⚠️ ${bs.error}` : '');

  const posMap = {'-1':['숏 (SHORT)','neg'], '0':['현금 대기','flat'], '1':['롱 (LONG)','pos']};
  const pm = posMap[String(bs.position ?? '')] || ['-','flat'];
  const pe = document.getElementById('position');
  let ptxt = pm[0];
  if (bs.upnl != null) ptxt += ` (${bs.upnl>=0?'+':''}${bs.upnl.toFixed(2)}%)`;
  pe.textContent = ptxt;
  pe.className = 'value ' + (bs.upnl != null ? (bs.upnl>=0?'pos':'neg') : pm[1]);
  document.getElementById('pricesig').textContent =
    bs.price ? `$${Math.round(bs.price).toLocaleString()} / ${({'-1':'숏','0':'현금','1':'롱'})[String(bs.signal)]||'-'}` : '-';
  document.getElementById('lastcheck').textContent = bs.time || '-';
  document.getElementById('cash').textContent =
    d.state.cash != null ? d.state.cash.toLocaleString(undefined,{maximumFractionDigits:0}) : '-';

  const sells = d.trades.filter(t => t.pnl_pct != null);
  const wins = sells.filter(t => t.pnl_pct > 0).length;
  const realized = sells.reduce((a,t)=>a+t.pnl_pct,0);
  const re = document.getElementById('realized');
  re.textContent = realized.toFixed(2)+'%'; re.className='value '+(realized>=0?'pos':'neg');
  document.getElementById('stats').textContent =
    sells.length ? `${sells.length}회 / ${(wins/sells.length*100).toFixed(0)}%` : '0회 / -';

  document.getElementById('trades').innerHTML = d.trades.slice().reverse().slice(0,50).map(t =>
    `<tr><td>${t.time}</td><td class="${t.side.toLowerCase()}">${t.side}</td>
     <td>${Math.round(t.price).toLocaleString()}</td><td>${Math.round(t.amount).toLocaleString()}</td>
     <td class="${(t.pnl_pct||0)>=0?'pos':'neg'}">${t.pnl_pct==null?'-':t.pnl_pct.toFixed(2)+'%'}</td></tr>`).join('');

  // ---- 가격 차트 + 매매 마커 ----
  const hist = d.history || [];
  const labels = hist.map(h=>h.t), prices = hist.map(h=>h.c);
  const mk = (sides, color, style, rot) => ({
    type:'scatter', data: d.trades
      .filter(t=>sides.includes(t.side))
      .map(t=>({x:nearestIdx(labels,t.time), y:t.price}))
      .filter(p=>p.x>=0),
    pointStyle:style, rotation:rot||0, radius:7, backgroundColor:color, borderColor:color });
  const cfg = { labels, datasets: [
    { type:'line', data: prices.map((p,i)=>({x:i, y:p})), borderColor:'#60a5fa',
      borderWidth:1.5, pointRadius:0, tension:.2 },
    mk(['LONG','BUY'], '#4ade80', 'triangle'),
    mk(['SHORT'], '#f87171', 'triangle', 180),
    mk(['CLOSE-L','CLOSE-S','SELL'], '#d1d5db', 'circle'),
  ]};
  const opts = { plugins:{legend:{display:false}}, animation:false,
    scales:{ x:{ type:'linear', ticks:{ color:'#8b90a0', maxTicksLimit:6,
                 callback:(v)=>labels[Math.round(v)]||'' } },
             y:{ ticks:{ color:'#8b90a0' } } } };
  if (!chart) chart = new Chart(document.getElementById('pxChart'), {data:cfg, options:opts});
  else { chart.data = cfg; chart.update('none'); }
}
refresh(); setInterval(refresh, 10000);
</script>
</body></html>"""


def _read(path, default):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            payload = {
                "state": _read("futures_state.json", _read("live_state.json", {})),
                "trades": _read("live_trades.json", []),
                "bot": _read("bot_status.json", {}),
                "history": _read("price_history.json", []),
            }
            self._send(json.dumps(payload, ensure_ascii=False).encode(),
                       "application/json")
        else:
            self._send(PAGE.encode(), "text/html")

    def do_POST(self):
        if self.path != "/api/control":
            return self._send(b'{"message":"not found"}', "application/json", 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n))
        except Exception:
            return self._send(b'{"message":"bad request"}', "application/json", 400)

        expected = os.environ.get("DASHBOARD_PASSWORD", "1234")
        if not hmac.compare_digest(str(body.get("password", "")), expected):
            return self._send(b'{"message":"forbidden"}', "application/json", 403)

        action = body.get("action")
        if action == "pause":
            Path("STOP").touch()
            msg = "일시정지 요청됨 (다음 폴링에서 포지션 청산 후 관망)"
        elif action == "resume":
            Path("STOP").unlink(missing_ok=True)
            msg = "재개 요청됨 (다음 폴링부터 매매 재개)"
        elif action == "close":
            Path("CLOSE_NOW").touch()
            msg = "수동 청산 요청됨 (다음 폴링에서 실행)"
        else:
            return self._send(b'{"message":"unknown action"}', "application/json", 400)
        self._send(json.dumps({"message": msg}, ensure_ascii=False).encode(),
                   "application/json")


if __name__ == "__main__":
    print(f"대시보드 실행: http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
