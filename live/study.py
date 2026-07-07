"""학습 진단 페이지 UI."""

STUDY_PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>학습 진단</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0A0E14; --panel:#11161F; --line:#1E2530; --tx:#D7DEE8; --mut:#6B7686;
          --ok:#00C077; --warn:#F5A623; --bad:#FF4D5E; --blue:#3E9DFF; }
  body { font-family:'IBM Plex Sans KR',sans-serif; background:var(--bg); color:var(--tx);
         margin:0; font-size:14px; }
  header { display:flex; align-items:center; gap:10px; padding:12px 16px;
           background:var(--panel); border-bottom:1px solid var(--line); }
  header h1 { font-size:14px; font-weight:700; margin:0; }
  header a { margin-left:auto; font-size:12px; color:var(--mut); text-decoration:none;
             border:1px solid var(--line); padding:5px 10px; border-radius:4px; }
  .wrap { padding:14px 16px 40px; }
  .row { display:flex; gap:8px; margin-bottom:12px; }
  select { flex:1; background:var(--panel); color:var(--tx); border:1px solid var(--line);
           border-radius:8px; padding:11px; font-size:14px; font-family:inherit; }
  h2 { font-family:'IBM Plex Mono',monospace; font-size:11px; color:var(--mut);
       letter-spacing:.12em; margin:18px 0 8px; }
  .grid { display:grid; grid-template-columns:repeat(5,1fr); gap:8px; }
  .q { background:var(--panel); border:1.5px solid var(--line); border-radius:10px;
       padding:9px 4px; text-align:center; cursor:pointer; user-select:none; }
  .q .no { font-family:'IBM Plex Mono',monospace; font-size:13px; font-weight:700; }
  .q .u { font-size:8.5px; color:var(--mut); margin-top:2px; white-space:nowrap;
          overflow:hidden; }
  .q.ok { border-color:var(--ok); background:#00C07715; }
  .q.ok .no { color:var(--ok); }
  .q.bad { border-color:var(--bad); background:#FF4D5E15; }
  .q.bad .no { color:var(--bad); text-decoration:line-through; }
  button.main { width:100%; padding:15px; font-size:15px; font-weight:800; border:0;
                border-radius:12px; background:var(--blue); color:#04121f;
                cursor:pointer; margin-top:16px; }
  .report { display:none; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:12px;
          padding:14px 16px; margin-bottom:12px; }
  .gapbox { display:flex; gap:10px; text-align:center; }
  .gapbox div { flex:1; }
  .gapbox .l { font-size:10px; color:var(--mut); font-family:'IBM Plex Mono',monospace; }
  .gapbox .v { font-size:22px; font-weight:800; font-family:'IBM Plex Mono',monospace; }
  .ubar { margin:7px 0; }
  .ubar .top { display:flex; justify-content:space-between; font-size:12px; }
  .ubar .track { height:7px; background:#1E2530; border-radius:4px; margin-top:4px; }
  .ubar .fill { height:100%; border-radius:4px; }
  .plan { border-left:3px solid var(--blue); padding:10px 12px; margin:10px 0;
          background:#3E9DFF0d; border-radius:0 8px 8px 0; }
  .plan b { color:var(--blue); }
  .plan .why { font-size:12px; color:var(--mut); margin-top:4px; line-height:1.6; }
  .verdict { font-size:13.5px; line-height:1.75; }
  .verdict b { color:var(--warn); }
</style></head>
<body>
<header><h1>🎯 학습 진단</h1><a href="/focus" style="margin-left:auto">📚</a><a href="/" style="margin-left:8px">콘솔</a></header>
<div class="wrap">
  <div class="row">
    <select id="subject" onchange="loadTemplate()">
      <option value="수학">수학</option><option value="국어">국어</option>
      <option value="영어">영어</option></select>
    <select id="sel"></select>
    <select id="grade"><option value="1">목표: 1등급</option>
      <option value="2" selected>목표: 2등급</option>
      <option value="3">목표: 3등급</option>
      <option value="4">목표: 4등급</option></select>
  </div>
  <h2>채점 입력 — 틀린 문항만 탭하세요 (기본=정답)</h2>
  <div class="grid" id="grid"></div>
  <button class="main" onclick="analyze()">진단 보고서 생성</button>

  <div class="report" id="report">
    <h2>DIAGNOSIS REPORT</h2>
    <div class="card gapbox">
      <div><div class="l">현재 점수</div><div class="v" id="rScore">-</div></div>
      <div><div class="l">목표 컷</div><div class="v" id="rTarget">-</div></div>
      <div><div class="l">부족 점수</div><div class="v" id="rGap" style="color:var(--bad)">-</div></div>
    </div>
    <div class="card"><h2 style="margin-top:0">단원별 정답률</h2><div id="rUnits"></div></div>
    <div class="card"><h2 style="margin-top:0">우선순위 학습 플랜</h2>
      <div class="verdict" id="rVerdict"></div><div id="rPlan"></div>
      <button class="main" id="goFocus" style="margin-top:10px;background:var(--ok)">
        📚 1순위 단원 공부 시작 (집중 트래커)</button></div>
    <div class="card"><h2 style="margin-top:0">성장 추이</h2><div id="growth"></div></div>
  </div>
</div>
<script>
let TEMPLATE = null, qs = [];

window.loadTemplate = async function() {
  const subject = document.getElementById('subject').value;
  const selEl = document.getElementById('sel');
  const r = await fetch('/api/study/template?subject=' + encodeURIComponent(subject) +
                        '&sel=' + encodeURIComponent(selEl.value || ''));
  TEMPLATE = await r.json();
  const sels = TEMPLATE.selects || [];
  selEl.style.display = sels.length ? '' : 'none';
  if (sels.length && ![...selEl.options].some(o => sels.includes(o.value)))
    selEl.innerHTML = sels.map(s => `<option value="${s}">선택: ${s}</option>`).join('');
  qs = TEMPLATE.questions.map(q => ({...q, correct: true}));
  renderGrid();
}
function renderGrid() {
  document.getElementById('grid').innerHTML = qs.map((q, i) =>
    `<div class="q ${q.correct ? 'ok' : 'bad'}" onclick="tap(${i})">
      <div class="no">${q.no}</div><div class="u">${q.unit}·${q.pts}점</div></div>`).join('');
}
window.tap = i => { qs[i].correct = !qs[i].correct; renderGrid(); };
document.getElementById('sel').onchange = loadTemplate;

window.analyze = async () => {
  const r = await fetch('/api/study/diagnose', { method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ questions: qs,
      subject: document.getElementById('subject').value,
      target_grade: document.getElementById('grade').value }) });
  const d = await r.json();
  document.getElementById('report').style.display = 'block';
  document.getElementById('rScore').textContent = d.score;
  document.getElementById('rTarget').textContent = d.target;
  document.getElementById('rGap').textContent = d.gap > 0 ? '-' + d.gap : '달성!';

  document.getElementById('rUnits').innerHTML = d.units.map(u => {
    const c = u.acc >= 75 ? 'var(--ok)' : u.acc >= 45 ? 'var(--warn)' : 'var(--bad)';
    return `<div class="ubar"><div class="top">
      <span>${u.unit} <span style="color:#6B7686;font-size:10.5px">(${u.n_ok}/${u.n})</span></span>
      <span style="color:${c};font-family:'IBM Plex Mono',monospace">${u.acc}%</span></div>
      <div class="track"><div class="fill" style="width:${u.acc}%;background:${c}"></div></div></div>`;
  }).join('');

  const top = d.plan[0];
  document.getElementById('rVerdict').innerHTML = !top
    ? '틀린 문항이 없습니다. 현재 실력 유지에 집중하세요.'
    : (d.gap <= 0
      ? `이미 목표 컷을 넘었습니다. 아래 취약 단원을 보강해 <b>안정권</b>을 굳히세요.`
      : `목표까지 <b>${d.gap}점</b>이 부족합니다. 잘하는 단원을 더 다듬는 것보다,
         아래 순서대로 취약 단원을 복구하는 것이 같은 시간 대비 점수 상승이 가장 큽니다.`);
  document.getElementById('rPlan').innerHTML = d.plan.map((p, i) =>
    `<div class="plan"><b>${i+1}순위 — ${p.unit}</b>
     <span style="float:right;font-family:'IBM Plex Mono',monospace;color:var(--ok)">+${p.gain}점 기대</span>
     <div class="why">현재 정답률 ${p.acc}% · 이 단원에서 ${p.lost}점을 잃고 있음.
     ${p.acc === 0 ? '전 문항 오답 — 개념 기초부터 재정비 필요.'
       : p.acc < 50 ? '기본 유형부터 복구하면 회복이 빠른 구간.'
       : '실수 유형 점검 위주로 짧게 보강.'}
     여기까지 완료 시 누적 +${p.cum}점${p.enough ? ' → <b style="color:var(--ok)">목표 도달 예상</b>' : ''}</div></div>`
  ).join('');
  const top1 = d.plan[0];
  document.getElementById('goFocus').onclick = () =>
    location.href = '/focus' + (top1 ? '?unit=' + encodeURIComponent(top1.unit) : '');
  drawGrowth();
  window.scrollTo({ top: document.getElementById('report').offsetTop, behavior:'smooth' });
};

async function drawGrowth() {
  const r = await fetch('/api/study/history');
  const subj = document.getElementById('subject').value;
  const rows = ((await r.json()).sessions || []).filter(s => (s.subject || '수학') === subj);
  if (rows.length < 2) {
    document.getElementById('growth').innerHTML =
      '<span style="color:#6B7686;font-size:12px">회차가 2번 이상 쌓이면 그래프가 그려집니다</span>';
    return;
  }
  const w = 300, h = 80, min = 0, max = 100;
  const pts = rows.map((s, i) =>
    `${(i / (rows.length - 1) * (w - 20) + 10).toFixed(1)},${(h - 10 - (s.score - min) / (max - min) * (h - 20)).toFixed(1)}`);
  const tgt = h - 10 - (rows[rows.length-1].target) / 100 * (h - 20);
  document.getElementById('growth').innerHTML =
    `<svg viewBox="0 0 ${w} ${h}" style="width:100%">
      <line x1="10" y1="${tgt}" x2="${w-10}" y2="${tgt}" stroke="#F5A623" stroke-dasharray="4 3" stroke-width="1"/>
      <polyline points="${pts.join(' ')}" fill="none" stroke="#3E9DFF" stroke-width="2"/>
      ${pts.map((p,i) => `<circle cx="${p.split(',')[0]}" cy="${p.split(',')[1]}" r="3" fill="#3E9DFF"/><text x="${p.split(',')[0]}" y="${parseFloat(p.split(',')[1])-7}" fill="#D7DEE8" font-size="9" text-anchor="middle">${rows[i].score}</text>`).join('')}
    </svg>
    <div style="font-size:10px;color:#6B7686">파란 선=회차 점수 · 노란 점선=목표 컷 (${subj}, 최근 ${rows.length}회)</div>`;
}
loadTemplate();
</script>
</body></html>"""
