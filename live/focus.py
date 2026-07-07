"""📚 셀프 집중 트래커.

프라이버시 원칙: 영상/이미지는 절대 서버로 전송하지 않는다.
MediaPipe FaceLandmarker(브라우저 내 실행)로 상태를 판별하고
세션 요약(시간·집중률 등 숫자)만 저장한다.

상태 판정:
- 자리비움: 얼굴 미검출 3초 지속
- 졸음: 양눈 감김(blendshape > 0.55) 1.5초 지속
- 딴짓: 고개 좌우 회전(yaw > 28도) 2초 지속
- 집중: 그 외
"""

FOCUS_PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>집중 트래커</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0A0E14; --panel:#11161F; --line:#1E2530; --tx:#D7DEE8; --mut:#6B7686;
          --ok:#00C077; --warn:#F5A623; --bad:#FF4D5E; --blue:#3E9DFF; }
  body { font-family:'IBM Plex Sans KR',sans-serif; background:var(--bg); color:var(--tx);
         margin:0; font-size:14px; }
  header { display:flex; align-items:center; gap:10px; padding:12px 16px;
           background:var(--panel); border-bottom:1px solid var(--line); }
  header h1 { font-size:14px; font-weight:700; margin:0; letter-spacing:.06em; }
  header a { margin-left:auto; font-size:12px; color:var(--mut); text-decoration:none;
             border:1px solid var(--line); padding:5px 10px; border-radius:4px; }
  .wrap { padding:14px 16px; }
  .cam { position:relative; border-radius:12px; overflow:hidden; background:#000;
         border:1px solid var(--line); }
  video { width:100%; display:block; transform:scaleX(-1); }
  .state { position:absolute; top:10px; left:10px; font-weight:800; font-size:15px;
           padding:7px 14px; border-radius:999px; background:#0009; backdrop-filter:blur(4px); }
  .privacy { font-size:11px; color:var(--mut); margin:8px 2px 14px; line-height:1.6; }
  .big { display:flex; gap:10px; margin-bottom:12px; }
  .card { flex:1; background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:12px 14px; }
  .card .l { font-family:'IBM Plex Mono',monospace; font-size:10px; color:var(--mut);
             letter-spacing:.1em; margin-bottom:4px; }
  .card .v { font-family:'IBM Plex Mono',monospace; font-size:20px; font-weight:600; }
  .bars { background:var(--panel); border:1px solid var(--line); border-radius:10px;
          padding:12px 14px; margin-bottom:12px; font-size:12.5px; }
  .bars div { display:flex; justify-content:space-between; padding:3px 0;
              font-family:'IBM Plex Mono',monospace; }
  button.main { width:100%; padding:16px; font-size:16px; font-weight:800; border:0;
                border-radius:12px; background:var(--ok); color:#04120a; cursor:pointer; }
  button.main.stop { background:var(--bad); color:#fff; }
  table { width:100%; border-collapse:collapse; font-family:'IBM Plex Mono',monospace;
          font-size:11.5px; margin-top:14px; }
  th, td { padding:7px 4px; text-align:right; border-bottom:1px solid var(--line); }
  th { color:var(--mut); font-size:10px; letter-spacing:.08em; }
  th:first-child, td:first-child { text-align:left; }
  .ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); }
</style></head>
<body>
<header><h1>📚 집중 트래커</h1><a href="/study" style="margin-left:auto">🎯</a><a href="/" style="margin-left:8px">콘솔</a></header>
<div id="goal" style="display:none;margin:12px 16px 0;padding:10px 14px;background:#3E9DFF14;
  border:1px solid #3E9DFF55;border-radius:10px;font-size:13px">
  🎯 오늘의 목표 단원: <b id="goalUnit" style="color:#3E9DFF"></b>
  <span style="color:#6B7686;font-size:11px">(진단 보고서 1순위)</span></div>
<div class="wrap">
  <div class="cam">
    <video id="cam" autoplay playsinline muted></video>
    <div class="state" id="state">대기 중</div>
  </div>
  <p class="privacy">🔒 영상은 이 기기 안에서만 분석되며 서버로 전송되지 않습니다.
  세션 종료 시 시간·집중률 요약 숫자만 저장됩니다.</p>
  <div class="big">
    <div class="card"><div class="l">SESSION</div><div class="v" id="tTotal">00:00</div></div>
    <div class="card"><div class="l">FOCUS RATE</div><div class="v ok" id="rate">-</div></div>
  </div>
  <div class="bars" id="bars">
    <div><span class="ok">● 집중</span><span id="tFocus">00:00</span></div>
    <div><span class="warn">● 졸음</span><span id="tDrowsy">00:00</span></div>
    <div><span class="warn">● 딴짓 (고개 돌림)</span><span id="tAway">00:00</span></div>
    <div><span class="bad">● 자리비움</span><span id="tGone">00:00</span></div>
  </div>
  <button class="main" id="btn" onclick="toggle()">▶ 세션 시작</button>
  <table>
    <thead><tr><th>날짜</th><th>시간</th><th>집중률</th><th>졸음</th><th>딴짓</th></tr></thead>
    <tbody id="hist"></tbody>
  </table>
</div>
<script type="module">
import { FaceLandmarker, FilesetResolver } from
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";

let lm = null, running = false, raf = null;
const goalUnit = new URLSearchParams(location.search).get('unit') || null;
if (goalUnit) {
  document.getElementById('goal').style.display = 'block';
  document.getElementById('goalUnit').textContent = goalUnit;
}
let t = { focus:0, drowsy:0, away:0, gone:0 };
let cur = 'idle', curSince = 0, lastTick = 0;
let pend = { state:null, since:0 };  // 상태 전환 지연 판정

const stateMeta = {
  focus: ['🟢 집중', 'var(--ok)'], drowsy: ['😴 졸음', 'var(--warn)'],
  away: ['👀 딴짓', 'var(--warn)'], gone: ['🚶 자리비움', 'var(--bad)'],
  idle: ['대기 중', 'var(--mut)'], loading: ['모델 로딩 중…', 'var(--blue)'] };

function fmt(s) { s = Math.floor(s);
  return String(Math.floor(s/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0'); }

function setState(s) {
  if (s === cur) return;
  cur = s;
  const [txt, col] = stateMeta[s];
  const el = document.getElementById('state');
  el.textContent = txt; el.style.color = col;
}

async function init() {
  setState('loading');
  const files = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm");
  lm = await FaceLandmarker.createFromOptions(files, {
    baseOptions: { modelAssetPath:
      "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" },
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: true,
    runningMode: "VIDEO", numFaces: 1 });
}

function judge(res) {
  if (!res.faceLandmarks || !res.faceLandmarks.length) return 'gone';
  const bs = {};
  (res.faceBlendshapes?.[0]?.categories || []).forEach(c => bs[c.categoryName] = c.score);
  const eyesClosed = (bs.eyeBlinkLeft || 0) > 0.55 && (bs.eyeBlinkRight || 0) > 0.55;
  let yaw = 0;
  const m = res.facialTransformationMatrixes?.[0]?.data;
  if (m) yaw = Math.abs(Math.atan2(m[8], m[10]) * 180 / Math.PI);
  if (eyesClosed) return 'drowsy';
  if (yaw > 28) return 'away';
  return 'focus';
}

// 상태별 확정 지연(초): 깜빡임/순간 회전 오탐 방지
const HOLD = { gone: 3, drowsy: 1.5, away: 2, focus: 0.5 };

function loop() {
  if (!running) return;
  const v = document.getElementById('cam');
  const now = performance.now();
  if (v.readyState >= 2) {
    const raw = judge(lm.detectForVideo(v, now));
    if (raw !== cur) {
      if (pend.state !== raw) { pend = { state: raw, since: now }; }
      else if ((now - pend.since) / 1000 >= HOLD[raw]) setState(raw);
    } else pend.state = null;
    const dt = lastTick ? (now - lastTick) / 1000 : 0;
    if (cur in t) t[cur] += dt;
    lastTick = now;
    render();
  }
  raf = requestAnimationFrame(loop);
}

function render() {
  const total = t.focus + t.drowsy + t.away + t.gone;
  document.getElementById('tTotal').textContent = fmt(total);
  document.getElementById('tFocus').textContent = fmt(t.focus);
  document.getElementById('tDrowsy').textContent = fmt(t.drowsy);
  document.getElementById('tAway').textContent = fmt(t.away);
  document.getElementById('tGone').textContent = fmt(t.gone);
  document.getElementById('rate').textContent =
    total > 5 ? (t.focus / total * 100).toFixed(0) + '%' : '-';
}

window.toggle = async function() {
  const btn = document.getElementById('btn');
  if (!running) {
    if (!lm) await init();
    const stream = await navigator.mediaDevices.getUserMedia(
      { video: { facingMode: 'user', width: 640 } });
    document.getElementById('cam').srcObject = stream;
    t = { focus:0, drowsy:0, away:0, gone:0 }; lastTick = 0;
    running = true; setState('focus');
    btn.textContent = '■ 세션 종료'; btn.classList.add('stop');
    loop();
  } else {
    running = false; cancelAnimationFrame(raf);
    const v = document.getElementById('cam');
    (v.srcObject?.getTracks() || []).forEach(tr => tr.stop());
    v.srcObject = null;
    btn.textContent = '▶ 세션 시작'; btn.classList.remove('stop');
    setState('idle');
    const total = t.focus + t.drowsy + t.away + t.gone;
    if (total > 30) {
      await fetch('/api/focus', { method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ total: Math.round(total), focus: Math.round(t.focus),
          drowsy: Math.round(t.drowsy), away: Math.round(t.away),
          gone: Math.round(t.gone), unit: goalUnit }) });
    }
    loadHist();
  }
};

async function loadHist() {
  const r = await fetch('/api/focus');
  const rows = (await r.json()).sessions || [];
  document.getElementById('hist').innerHTML = rows.slice().reverse().slice(0, 30).map(s => {
    const rate = s.total ? (s.focus / s.total * 100).toFixed(0) : 0;
    const cls = rate >= 80 ? 'ok' : rate >= 60 ? 'warn' : 'bad';
    return `<tr><td>${s.time}</td><td>${fmt(s.total)}</td>
      <td class="${cls}">${rate}%</td><td>${fmt(s.drowsy)}</td><td>${fmt(s.away)}</td></tr>`;
  }).join('') || '<tr><td colspan="5" style="color:#6B7686">아직 기록 없음</td></tr>';
}
loadHist();
</script>
</body></html>"""
