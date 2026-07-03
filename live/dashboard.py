"""실시간 매매 모니터링 + 제어 웹 대시보드 v2.

기능: 가격 차트에 진입/청산 마커, 봇 일시정지/재개, 수동 청산, 상태 표시.
제어 버튼은 DASHBOARD_PASSWORD 환경변수(기본 "1234")로 보호된다.

로컬 사용법:
  python -m live.dashboard   # http://localhost:8800
"""
import hmac
import json
import os
import time as _time
import uuid

from live.mission import MISSION_PAGE

_CANDLE_CACHE = {}  # tf -> (timestamp, data)
_TF_OK = ["1m", "5m", "30m", "1h", "4h", "1d"]


def _fetch_candles_api(tf: str):
    """시간프레임별 캔들 (KST 라벨, 15초 캐시)."""
    now = _time.time()
    if tf in _CANDLE_CACHE and now - _CANDLE_CACHE[tf][0] < 15:
        return _CANDLE_CACHE[tf][1]
    try:
        if os.environ.get("FAKE_CANDLES"):  # 오프라인 테스트용
            import random
            random.seed(hash(tf) % 1000)
            px, out = 60000.0, []
            for i in range(120):
                o = px
                c = o * (1 + random.uniform(-0.01, 0.01))
                h = max(o, c) * (1 + random.uniform(0, 0.005))
                l = min(o, c) * (1 - random.uniform(0, 0.005))
                out.append({"t": f"07-02 {i//60:02d}:{i%60:02d}",
                            "o": o, "h": h, "l": l, "c": c})
                px = c
        else:
            import ccxt
            from datetime import datetime, timezone, timedelta
            KST = timezone(timedelta(hours=9))
            ex = ccxt.bybit({"options": {"defaultType": "swap"}})
            symbol = os.environ.get("SYMBOL", "BTC/USDT:USDT")
            rows = ex.fetch_ohlcv(symbol, timeframe=tf, limit=120)
            fmt = "%m-%d" if tf == "1d" else "%m-%d %H:%M"
            out = [{"t": datetime.fromtimestamp(r[0] / 1000, KST).strftime(fmt),
                    "o": r[1], "h": r[2], "l": r[3], "c": r[4]} for r in rows]
        _CANDLE_CACHE[tf] = (now, out)
        return out
    except Exception:
        return _CANDLE_CACHE.get(tf, (0, []))[1]
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

PORT = 8800
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)

PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TRADING CONSOLE</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root { color-scheme: dark;
    --bg:#0A0E14; --panel:#11161F; --line:#1E2530; --line2:#2A3342;
    --tx:#D7DEE8; --mut:#6B7686; --up:#00C077; --dn:#FF4D5E;
    --amber:#F5A623; --blue:#3E9DFF; }
  * { box-sizing:border-box; }
  body { font-family:'IBM Plex Sans KR',sans-serif; background:var(--bg);
         color:var(--tx); margin:0; font-size:14px; }
  .mono { font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums; }

  /* ── 상단 상태 바 ── */
  header { display:flex; align-items:center; gap:10px; padding:12px 16px;
           border-bottom:1px solid var(--line); background:var(--panel); }
  .led { width:8px; height:8px; border-radius:50%; background:var(--up);
         box-shadow:0 0 6px var(--up); animation:pulse 2s infinite; }
  .led.pause { background:var(--amber); box-shadow:0 0 6px var(--amber); animation:none; }
  .led.err { background:var(--dn); box-shadow:0 0 6px var(--dn); animation:none; }
  @keyframes pulse { 50% { opacity:.35; } }
  @media (prefers-reduced-motion: reduce) { .led { animation:none; } }
  header h1 { font-size:13px; font-weight:700; letter-spacing:.12em; margin:0; }
  .hdr-meta { margin-left:auto; display:flex; gap:6px; align-items:center; }
  .tag { font-family:'IBM Plex Mono',monospace; font-size:10px; letter-spacing:.08em;
         padding:3px 8px; border:1px solid var(--line2); border-radius:3px; color:var(--mut); }
  .tag.live { color:var(--dn); border-color:var(--dn); }
  .tag.i { cursor:pointer; }
  #botinfo { font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--mut);
             padding:7px 16px; border-bottom:1px solid var(--line); }

  /* ── 시그니처: 포지션 티켓 ── */
  .ticket { display:flex; align-items:stretch; margin:14px 16px 0;
            background:var(--panel); border:1px solid var(--line); border-radius:4px;
            overflow:hidden; }
  .ticket .side { width:6px; background:var(--mut); }
  .ticket.long .side { background:var(--up); }
  .ticket.short .side { background:var(--dn); }
  .ticket .body { flex:1; padding:12px 14px; }
  .eyebrow { font-family:'IBM Plex Mono',monospace; font-size:10px;
             letter-spacing:.14em; color:var(--mut); margin-bottom:4px; }
  #tkSide { font-size:15px; font-weight:700; }
  .ticket.long #tkSide { color:var(--up); } .ticket.short #tkSide { color:var(--dn); }
  .ticket .pnl { text-align:right; padding:12px 14px; border-left:1px dashed var(--line2); }
  #tkPnl { font-family:'IBM Plex Mono',monospace; font-size:26px; font-weight:600;
           transition:color .3s; }
  #tkPnl.pos { color:var(--up); } #tkPnl.neg { color:var(--dn); } #tkPnl.flat { color:var(--mut); }
  #tkDetail { font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--mut); margin-top:3px; }

  /* ── 제어 ── */
  .controls { display:flex; gap:8px; padding:12px 16px; }
  button { font-family:'IBM Plex Sans KR',sans-serif; font-size:13px; font-weight:500;
           padding:9px 14px; border-radius:4px; border:1px solid var(--line2);
           background:var(--panel); color:var(--tx); cursor:pointer; }
  button:focus-visible { outline:2px solid var(--blue); outline-offset:1px; }
  #toggleBtn.pausebtn { border-color:var(--amber); color:var(--amber); }
  #toggleBtn.resumebtn { border-color:var(--up); color:var(--up); }
  .closebtn { border-color:var(--line2); color:var(--mut); }

  /* ── 데이터 그리드 ── */
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:1px;
          background:var(--line); border:1px solid var(--line); margin:0 16px;
          border-radius:4px; overflow:hidden; }
  .cell { background:var(--panel); padding:11px 14px; }
  .cell .v { font-family:'IBM Plex Mono',monospace; font-size:17px; font-weight:500; }
  .v.pos { color:var(--up); } .v.neg { color:var(--dn); } .v.small { font-size:12px; }

  /* ── 차트 ── */
  .panel { margin:14px 16px; background:var(--panel); border:1px solid var(--line);
           border-radius:4px; padding:12px 14px; }
  .panel-title { display:flex; justify-content:space-between; align-items:baseline;
                 margin-bottom:8px; }
  .legend { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--mut); }
  .tfbar { display:flex; gap:4px; margin-bottom:10px; }
  .tf { font-family:'IBM Plex Mono',monospace; font-size:11px; padding:5px 10px;
        border:1px solid var(--line2); border-radius:3px; background:transparent;
        color:var(--mut); cursor:pointer; }
  .tf.on { border-color:var(--blue); color:var(--blue); }
  .legend .u{color:var(--up)} .legend .d{color:var(--dn)}

  /* ── 체결 블로터 ── */
  table { width:100%; border-collapse:collapse; font-family:'IBM Plex Mono',monospace;
          font-size:11.5px; }
  th { font-size:10px; letter-spacing:.1em; color:var(--mut); font-weight:500;
       border-bottom:1px solid var(--line2); padding:6px 4px; text-align:right; }
  td { padding:7px 4px; text-align:right; border-bottom:1px solid var(--line); }
  th:first-child, td:first-child { text-align:left; }
  tr:last-child td { border-bottom:0; }
  .buy,.long { color:var(--up); } .sell,.short,.close-l,.close-s { color:var(--dn); }
  .pos { color:var(--up); } .neg { color:var(--dn); } .flat { color:var(--mut); }
  .muted { color:var(--mut); font-size:11px; padding:0 16px 20px;
           font-family:'IBM Plex Mono',monospace; }

  /* ── 소개 ── */
  .intro { display:none; margin:14px 16px 0; background:var(--panel);
           border:1px solid var(--line); border-radius:4px; padding:4px 16px 12px;
           font-size:13px; line-height:1.7; color:#AEB7C4; }
  .intro.open { display:block; }
  .intro h2 { font-family:'IBM Plex Mono',monospace; font-size:11px; letter-spacing:.12em;
              color:var(--blue); margin:14px 0 4px; }
  .intro p { margin:4px 0; }
</style></head>
<body>
<header>
  <span id="led" class="led"></span>
  <h1>TRADING CONSOLE</h1>
  <div class="hdr-meta">
    <span id="modebadge" class="tag">…</span>
    <span id="badge" class="tag">…</span>
    <span class="tag i" onclick="document.getElementById('intro').classList.toggle('open')">INFO</span>
    <a class="tag i" href="/" style="text-decoration:none">전도 지도</a>
  </div>
</header>
<div id="botinfo">connecting…</div>

<div id="intro" class="intro">
  <h2>OVERVIEW</h2>
  <p>비트코인 무기한 선물을 <b>돈치안 채널 롱숏</b> 전략으로 24시간 자동매매하는 봇입니다.
  최근 40봉(약 6.7일) <b>최고가를 돌파하면 롱</b>, <b>최저가를 이탈하면 숏</b>으로 추세를 따라가는
  추세추종 방식으로, 터틀 트레이딩에서 검증된 로직의 양방향 버전입니다.</p>
  <h2>STRATEGY PROFILE</h2>
  <p>승률은 낮은 편(35~50%)이지만 추세를 한번 타면 크게 수익을 내는 <b>손익비형 전략</b>입니다.
  횡보장에서 잔손실이 이어지는 것은 정상 작동이며, 2025~2026 하락장 백테스트(미접촉 검증)에서
  시장 -33% 대비 +39.6%를 기록했습니다. 과거 성과가 미래 수익을 보장하지는 않습니다.</p>
  <h2>SAFEGUARDS</h2>
  <p>레버리지 1배 고정 · 진입가 대비 -5% 자동 손절(직후 재진입 금지) · 포지션 금액 상한 ·
  일시정지/수동 청산(비밀번호 보호) · 마감된 봉만 사용해 가짜 돌파 차단.</p>
  <p style="color:var(--amber)">투자 손실은 전적으로 본인 책임입니다. 모의로 검증 후 소액만 운용하세요.</p>
</div>

<div class="ticket" id="ticket">
  <div class="side"></div>
  <div class="body">
    <div class="eyebrow">POSITION · 포지션</div>
    <div id="tkSide">-</div>
    <div id="tkDetail">-</div>
  </div>
  <div class="pnl">
    <div class="eyebrow">UNREALIZED P&L</div>
    <div id="tkPnl" class="flat">-</div>
  </div>
</div>

<div class="controls">
  <button id="toggleBtn" class="pausebtn" onclick="control()">일시정지</button>
  <button class="closebtn" onclick="control('close')">수동 청산</button>
  <button id="modeBtn" class="closebtn" onclick="switchMode()">실계좌 전환</button>
</div>
<div id="keyForm" class="intro" style="margin-top:0">
  <h2>BYBIT API KEYS</h2>
  <p id="keyStatus" style="font-family:'IBM Plex Mono',monospace"></p>
  <p>Bybit → API 관리에서 생성한 키를 입력하세요. 권한은 <b>Contract Trade만</b>,
  <b style="color:var(--dn)">출금(Withdrawal)은 반드시 해제</b>. 저장된 시크릿은 다시 표시되지 않습니다.</p>
  <p><input id="kIn" placeholder="API Key" style="width:100%;margin:3px 0;padding:9px;border:1px solid var(--line2);border-radius:4px;background:var(--bg);color:var(--tx);font-family:'IBM Plex Mono',monospace"></p>
  <p><input id="sIn" placeholder="API Secret" type="password" style="width:100%;margin:3px 0;padding:9px;border:1px solid var(--line2);border-radius:4px;background:var(--bg);color:var(--tx);font-family:'IBM Plex Mono',monospace"></p>
  <p style="display:flex;gap:8px">
    <button onclick="saveKeys()">키 저장</button>
    <button class="closebtn" onclick="deleteKeys()">키 삭제</button>
  </p>
</div>

<div class="grid">
  <div class="cell"><div class="eyebrow">LAST PRICE · 현재가/시그널</div><div class="v" id="pricesig">-</div></div>
  <div class="cell"><div class="eyebrow">BALANCE · 잔고 USDT</div><div class="v" id="cash">-</div></div>
  <div class="cell"><div class="eyebrow">UNREALIZED · 평가손익 (실시간)</div><div class="v" id="unreal">-</div></div>
  <div class="cell"><div class="eyebrow">REALIZED · 실현수익(청산분)</div><div class="v" id="realized">-</div></div>
  <div class="cell"><div class="eyebrow">TRADES · 거래/승률</div><div class="v" id="stats">-</div></div>
  <div class="cell" style="grid-column:1/-1"><div class="eyebrow">LAST CHECK · 마지막 체크 (KST)</div><div class="v small" id="lastcheck">-</div></div>
</div>

<div class="panel">
  <div class="panel-title">
    <span class="eyebrow">PRICE &amp; EXECUTIONS</span>
    <span class="legend"><span class="u">▲ LONG</span> · <span class="d">▼ SHORT</span> · ● CLOSE</span>
  </div>
  <div class="tfbar" id="tfbar">
    <button class="tf" data-tf="1m">1m</button>
    <button class="tf" data-tf="5m">5m</button>
    <button class="tf" data-tf="30m">30m</button>
    <button class="tf on" data-tf="1h">1H</button>
    <button class="tf" data-tf="4h">4H</button>
    <button class="tf" data-tf="1d">1D</button>
  </div>
  <canvas id="pxChart" height="150"></canvas>
</div>

<div class="panel">
  <div class="panel-title"><span class="eyebrow">EXECUTION BLOTTER · 체결 내역</span></div>
  <table>
    <thead><tr><th>TIME</th><th>SIDE</th><th>PRICE</th><th>NOTIONAL</th><th>P&L</th></tr></thead>
    <tbody id="trades"></tbody>
  </table>
</div>
<p class="muted">AUTO-REFRESH 10s · CONTROL REQUIRES PASSWORD</p>
<script>
let chart, paused=false;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

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
let curMode='PAPER', liveReady=false, keysSet=false;
async function saveKeys() {
  const p = pw(); if (!p) return;
  const k = document.getElementById('kIn').value, s = document.getElementById('sIn').value;
  const r = await fetch('/api/control', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action:'save_keys', password:p, key:k, secret:s}) });
  if (r.status === 403) { sessionStorage.removeItem('pw'); alert('비밀번호가 틀렸습니다'); return; }
  const d = await r.json(); alert(d.message);
  document.getElementById('kIn').value=''; document.getElementById('sIn').value='';
  refresh();
}
async function deleteKeys() {
  if (!confirm('저장된 API 키를 삭제하고 모의 모드로 전환할까요?')) return;
  const p = pw(); if (!p) return;
  const r = await fetch('/api/control', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({action:'delete_keys', password:p}) });
  const d = await r.json(); alert(d.message); refresh();
}
function switchMode() {
  if (curMode === 'LIVE') {
    if (confirm('모의(PAPER) 모드로 전환할까요? 실계좌 포지션은 청산됩니다.')) control('paper');
    return;
  }
  if (!liveReady) {
    document.getElementById('keyForm').classList.add('open');
    alert(keysSet
      ? '먼저 Railway Variables에서 DASHBOARD_PASSWORD를 기본값에서 변경하세요.'
      : 'API 키가 없습니다. 아래 폼에 Bybit API 키를 입력해 저장한 뒤 다시 눌러주세요.');
    return;
  }
  if (!confirm('경고: 실제 자금으로 매매하는 실계좌(LIVE) 모드로 전환합니다. 손실은 본인 책임입니다. 계속할까요?')) return;
  if (prompt('확인을 위해 LIVE 를 입력하세요') !== 'LIVE') { alert('전환 취소됨'); return; }
  control('live');
}
function nearestIdx(labels, t) {
  const key = t.slice(5,16).replace('T',' ');
  let best=-1;
  for (let i=0;i<labels.length;i++) if (labels[i] <= key) best=i;
  return best;
}
async function refresh() {
  const r = await fetch('/api/status'); const d = await r.json();
  const bs = d.bot || {};
  paused = !!bs.paused;

  const led = document.getElementById('led');
  const badge = document.getElementById('badge');
  if (bs.error) { badge.textContent='ERROR'; badge.style.color=css('--dn'); led.className='led err'; }
  else if (paused) { badge.textContent='PAUSED'; badge.style.color=css('--amber'); led.className='led pause'; }
  else { badge.textContent='RUNNING'; badge.style.color=css('--up'); led.className='led'; }
  const mb = document.getElementById('modebadge');
  curMode = bs.mode || 'PAPER'; liveReady = !!d.live_ready; keysSet = !!d.keys_set;
  document.getElementById('keyStatus').textContent =
    d.keys_set ? `등록된 키: ${d.key_masked || '설정됨'}` : '등록된 키 없음';
  if (curMode === 'LIVE') { mb.textContent='LIVE'; mb.className='tag live'; }
  else { mb.textContent='PAPER'; mb.className='tag'; }
  const mBtn = document.getElementById('modeBtn');
  mBtn.textContent = curMode === 'LIVE' ? '모의로 전환' : '실계좌 전환';
  mBtn.style.borderColor = curMode === 'LIVE' ? css('--dn') : '';
  mBtn.style.color = curMode === 'LIVE' ? css('--dn') : '';

  const tb = document.getElementById('toggleBtn');
  tb.textContent = paused ? '매매 재개' : '일시정지';
  tb.className = paused ? 'resumebtn' : 'pausebtn';

  document.getElementById('botinfo').textContent =
    `${bs.strategy||''}  ·  ${bs.symbol||''}  ·  ${bs.interval||''}` +
    (bs.error ? `  ·  ⚠ ${bs.error}` : '');

  // ── 포지션 티켓 ──
  const qty = d.state.qty || 0, entry = d.state.entry_price || 0;
  const pnow = (d.price_now && d.price_now.price) || bs.price;
  const ticket = document.getElementById('ticket');
  const tkSide = document.getElementById('tkSide');
  const tkPnl = document.getElementById('tkPnl');
  const tkDetail = document.getElementById('tkDetail');
  if (qty && entry && pnow) {
    const isLong = qty > 0;
    const upnl = (pnow/entry - 1) * (isLong?1:-1) * 100;
    ticket.className = 'ticket ' + (isLong?'long':'short');
    tkSide.textContent = isLong ? 'LONG 롱' : 'SHORT 숏';
    tkPnl.textContent = (upnl>=0?'+':'') + upnl.toFixed(2) + '%';
    tkPnl.className = upnl>=0 ? 'pos' : 'neg';
    tkDetail.textContent = `ENTRY ${Math.round(entry).toLocaleString()}  →  NOW ${Math.round(pnow).toLocaleString()}`;
    const un = document.getElementById('unreal');
    un.textContent = (upnl>=0?'+':'') + upnl.toFixed(2) + '%';
    un.className = 'v ' + (upnl>=0?'pos':'neg');
  } else {
    ticket.className = 'ticket';
    tkSide.textContent = '현금 대기 FLAT';
    tkPnl.textContent = '-'; tkPnl.className = 'flat';
    tkDetail.textContent = pnow ? `NOW ${Math.round(pnow).toLocaleString()}` : '-';
    const un = document.getElementById('unreal');
    un.textContent = '-'; un.className = 'v flat';
  }

  document.getElementById('pricesig').textContent =
    pnow ? `${Math.round(pnow).toLocaleString()} / ${({'-1':'숏','0':'현금','1':'롱'})[String(bs.signal)]||'-'}` : '-';
  document.getElementById('lastcheck').textContent = bs.time || '-';
  document.getElementById('cash').textContent =
    d.state.cash != null ? d.state.cash.toLocaleString(undefined,{maximumFractionDigits:0}) : '-';

  const sells = d.trades.filter(t => t.pnl_pct != null);
  const wins = sells.filter(t => t.pnl_pct > 0).length;
  const realized = sells.reduce((a,t)=>a+t.pnl_pct,0);
  const re = document.getElementById('realized');
  re.textContent = (realized>=0?'+':'') + realized.toFixed(2)+'%';
  re.className = 'v ' + (realized>=0?'pos':'neg');
  document.getElementById('stats').textContent =
    sells.length ? `${sells.length} / ${(wins/sells.length*100).toFixed(0)}%` : '0 / -';

  const lastEntryIdx = (()=>{ // 미청산 진입 거래의 원본 인덱스
    if (!qty) return -1;
    for (let i=d.trades.length-1;i>=0;i--)
      if (['LONG','SHORT'].includes(d.trades[i].side)) return i;
    return -1; })();
  document.getElementById('trades').innerHTML = d.trades.map((t,i)=>({t,i})).reverse().slice(0,50).map(({t,i}) =>
    `<tr><td>${t.time.slice(5,16)}</td><td class="${t.side.toLowerCase()}">${t.side}</td>
     <td>${Math.round(t.price).toLocaleString()}</td><td>${Math.round(t.amount).toLocaleString()}</td>
     <td class="${(t.pnl_pct ?? (i===lastEntryIdx?((pnow/entry-1)*(qty>0?1:-1)*100):0))>=0?'pos':'neg'}">${
       t.pnl_pct!=null ? (t.pnl_pct>=0?'+':'')+t.pnl_pct.toFixed(2)+'%'
       : (i===lastEntryIdx && entry && pnow)
         ? '◉ '+(((pnow/entry-1)*(qty>0?1:-1)*100)>=0?'+':'')+((pnow/entry-1)*(qty>0?1:-1)*100).toFixed(2)+'%'
         : '-'}</td></tr>`).join('');

  // 거래 마커용 최신 데이터 보관
  window._trades = d.trades; window._pos = {qty, entry, pnow};
  drawChart();
}

let curTf = '1h', candleCache = null, candleTfLoaded = null, lastCandleFetch = 0;
document.getElementById('tfbar').addEventListener('click', e => {
  const b = e.target.closest('.tf'); if (!b) return;
  document.querySelectorAll('.tf').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');
  curTf = b.dataset.tf; candleCache = null; lastCandleFetch = 0;
  drawChart();
});

async function drawChart() {
  const now = Date.now();
  if (!candleCache || candleTfLoaded !== curTf || now - lastCandleFetch > 15000) {
    try {
      const r = await fetch('/api/candles?tf=' + curTf);
      const j = await r.json();
      if (j.candles && j.candles.length) {
        candleCache = j.candles; candleTfLoaded = curTf; lastCandleFetch = now;
      }
    } catch(e) {}
  }
  const cs = candleCache || [];
  const labels = cs.map(c=>c.t);
  const up = css('--up'), dn = css('--dn');
  const colors = cs.map(c => c.c >= c.o ? up : dn);
  const trades = window._trades || [];
  const mk = (sides, color, style, rot) => ({
    type:'scatter', data: trades
      .filter(t=>sides.includes(t.side))
      .map(t=>({x:nearestIdx(labels,t.time), y:t.price}))
      .filter(p=>p.x>=0),
    pointStyle:style, rotation:rot||0, radius:6,
    backgroundColor:color, borderColor:color, order:0 });
  const cfg = { labels, datasets: [
    { type:'bar', data: cs.map(c=>[c.l, c.h]), backgroundColor:colors,
      barPercentage:0.18, categoryPercentage:1.0, grouped:false, order:2 },   // 심지
    { type:'bar', data: cs.map(c=>[Math.min(c.o,c.c), Math.max(c.o,c.c)]),
      backgroundColor:colors, barPercentage:0.75, categoryPercentage:1.0,
      grouped:false, order:1 },                                               // 몸통
    mk(['LONG','BUY'], up, 'triangle'),
    mk(['SHORT'], dn, 'triangle', 180),
    mk(['CLOSE-L','CLOSE-S','SELL'], '#AEB7C4', 'circle'),
  ]};
  const opts = { plugins:{legend:{display:false}}, animation:false,
    scales:{ x:{ stacked:false, grid:{color:'#1E2530'},
                 ticks:{ color:'#6B7686', maxTicksLimit:6, maxRotation:0,
                         font:{family:'IBM Plex Mono', size:9} } },
             y:{ grid:{color:'#1E2530'}, beginAtZero:false,
                 ticks:{ color:'#6B7686', font:{family:'IBM Plex Mono', size:9} } } } };
  if (!chart) chart = new Chart(document.getElementById('pxChart'), {data:cfg, options:opts});
  else { chart.data = cfg; chart.update('none'); }
}
refresh(); setInterval(refresh, 10000);
</script>
</body></html>"""


def _keys_present():
    if os.environ.get("BYBIT_KEY") and os.environ.get("BYBIT_SECRET"):
        return True
    return (DATA_DIR / "bybit_keys.json").exists()


def _key_masked():
    if os.environ.get("BYBIT_KEY"):
        return os.environ["BYBIT_KEY"][:4] + "····" + " (환경변수)"
    p = DATA_DIR / "bybit_keys.json"
    if p.exists():
        try:
            k = json.loads(p.read_text()).get("key", "")
            return k[:4] + "····"
        except Exception:
            return None
    return None


def _read(path, default):
    p = DATA_DIR / path
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
        if self.path.startswith("/api/candles"):
            tf = (self.path.split("tf=")[-1] if "tf=" in self.path else "1h")
            tf = tf if tf in _TF_OK else "1h"
            return self._send(json.dumps({"tf": tf, "candles": _fetch_candles_api(tf)},
                                         ensure_ascii=False).encode(), "application/json")
        if self.path == "/api/mission":
            return self._send(json.dumps(
                {"spots": _read("mission_spots.json", [])}, ensure_ascii=False).encode(),
                "application/json")
        if self.path == "/api/status":
            payload = {
                "state": _read("futures_state.json", _read("live_state.json", {})),
                "trades": _read("live_trades.json", []),
                "bot": _read("bot_status.json", {}),
                "history": _read("price_history.json", []),
                "price_now": _read("price_now.json", {}),
                "live_ready": _keys_present()
                              and os.environ.get("DASHBOARD_PASSWORD", "1234") != "1234",
                "keys_set": _keys_present(),
                "key_masked": _key_masked(),
            }
            self._send(json.dumps(payload, ensure_ascii=False).encode(),
                       "application/json")
        elif self.path.startswith("/console"):
            self._send(PAGE.encode(), "text/html")
        else:
            self._send(MISSION_PAGE.encode(), "text/html")

    def do_POST(self):
        if self.path == "/api/mission":
            return self._mission_post()
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
            (DATA_DIR / "STOP").touch()
            msg = "일시정지 요청됨 (다음 폴링에서 포지션 청산 후 관망)"
        elif action == "resume":
            (DATA_DIR / "STOP").unlink(missing_ok=True)
            msg = "재개 요청됨 (다음 폴링부터 매매 재개)"
        elif action == "close":
            (DATA_DIR / "CLOSE_NOW").touch()
            msg = "수동 청산 요청됨 (다음 폴링에서 실행)"
        elif action == "live":
            ready = (_keys_present()
                     and os.environ.get("DASHBOARD_PASSWORD", "1234") != "1234")
            if not ready:
                return self._send(json.dumps({"message":
                    "실계좌 전환 불가: API 키를 등록(폼 또는 Railway Variables)하고 "
                    "DASHBOARD_PASSWORD를 기본값에서 변경하세요."}, ensure_ascii=False).encode(),
                    "application/json", 400)
            (DATA_DIR / "MODE").write_text("LIVE")
            msg = "⚠️ 실계좌(LIVE) 전환 요청됨. 다음 폴링에서 모의 포지션 청산 후 실계좌 매매 시작"
        elif action == "paper":
            (DATA_DIR / "MODE").write_text("PAPER")
            msg = "모의(PAPER) 전환 요청됨. 다음 폴링에서 실계좌 포지션 청산 후 모의로 복귀"
        elif action == "save_keys":
            if os.environ.get("DASHBOARD_PASSWORD", "1234") == "1234":
                return self._send(json.dumps({"message":
                    "먼저 Railway Variables에서 DASHBOARD_PASSWORD를 변경하세요. "
                    "기본 비밀번호로는 키를 저장할 수 없습니다."}, ensure_ascii=False).encode(),
                    "application/json", 400)
            k = str(body.get("key", "")).strip()
            s = str(body.get("secret", "")).strip()
            if len(k) < 6 or len(s) < 6:
                return self._send(json.dumps({"message": "키 형식이 올바르지 않습니다."},
                    ensure_ascii=False).encode(), "application/json", 400)
            p = DATA_DIR / "bybit_keys.json"
            p.write_text(json.dumps({"key": k, "secret": s}))
            try:
                os.chmod(p, 0o600)
            except Exception:
                pass
            msg = f"API 키 저장됨 ({k[:4]}····). 이제 '실계좌 전환'을 누르면 LIVE로 전환됩니다."
        elif action == "delete_keys":
            (DATA_DIR / "bybit_keys.json").unlink(missing_ok=True)
            (DATA_DIR / "MODE").write_text("PAPER")
            msg = "API 키 삭제됨. 모의(PAPER)로 전환합니다."
        else:
            return self._send(b'{"message":"unknown action"}', "application/json", 400)
        self._send(json.dumps({"message": msg}, ensure_ascii=False).encode(),
                   "application/json")

    def _mission_post(self):
        # 전도 지도는 누구나 기록 가능 (비밀번호 없음)
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n))
        except Exception:
            return self._send(b'{"message":"bad request"}', "application/json", 400)

        from datetime import datetime, timezone, timedelta
        spots = _read("mission_spots.json", [])
        action = body.get("action")
        if action == "add":
            spots.append({
                "id": uuid.uuid4().hex[:8],
                "lat": float(body["lat"]), "lng": float(body["lng"]),
                "name": str(body.get("name", ""))[:60],
                "status": body.get("status") if body.get("status") in ("done", "todo", "pickup") else "todo",
                "time": datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
            })
        elif action in ("toggle", "status"):
            new = body.get("status")
            for s in spots:
                if s["id"] == body.get("id"):
                    if new in ("done", "todo", "pickup"):
                        s["status"] = new
                    else:  # 구버전 toggle 호환
                        s["status"] = "todo" if s["status"] == "done" else "done"
                    s["time"] = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
        elif action == "delete":
            spots = [s for s in spots if s["id"] != body.get("id")]
        else:
            return self._send(b'{"message":"unknown action"}', "application/json", 400)
        (DATA_DIR / "mission_spots.json").write_text(
            json.dumps(spots, ensure_ascii=False, indent=1))
        self._send(json.dumps({"spots": spots}, ensure_ascii=False).encode(),
                   "application/json")


if __name__ == "__main__":
    print(f"대시보드 실행: http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
