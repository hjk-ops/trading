"""전도 지도 페이지 (Leaflet + OpenStreetMap).

- 탭하여 방문 지점 기록, 완료(초록)/예정(노랑) 토글, 삭제
- 데이터는 DATA_DIR/mission_spots.json 저장 (볼륨 사용 시 영구 보존)
- 추가/수정/삭제는 대시보드와 동일한 비밀번호로 보호
"""

MISSION_PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>전도 지도</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0A0E14; --panel:#11161F; --line:#1E2530; --tx:#D7DEE8;
          --mut:#6B7686; --done:#00C077; --todo:#F5A623; --blue:#3E9DFF; }
  html, body { height:100%; margin:0; }
  body { font-family:'IBM Plex Sans KR',sans-serif; background:var(--bg);
         color:var(--tx); display:flex; flex-direction:column; }
  header { display:flex; align-items:center; gap:10px; padding:12px 16px;
           background:var(--panel); border-bottom:1px solid var(--line); z-index:1000; }
  header h1 { font-size:14px; font-weight:700; letter-spacing:.08em; margin:0; }
  nav { margin-left:auto; display:flex; gap:8px; }
  nav a, .navbtn { font-size:12px; color:var(--mut); text-decoration:none;
    border:1px solid var(--line); padding:5px 10px; border-radius:4px;
    background:transparent; cursor:pointer; font-family:inherit; }
  .navbtn.on { border-color:var(--blue); color:var(--blue); }
  #map { flex:1; }
  .stats { position:fixed; bottom:14px; left:50%; transform:translateX(-50%);
           background:var(--panel); border:1px solid var(--line); border-radius:999px;
           padding:8px 18px; font-size:13px; z-index:1000; display:flex; gap:14px; }
  .stats b.d { color:var(--done); } .stats b.t { color:var(--todo); }
  .leaflet-popup-content-wrapper { background:var(--panel); color:var(--tx);
    border:1px solid var(--line); border-radius:8px; }
  .leaflet-popup-tip { background:var(--panel); }
  .pop b { font-size:14px; }
  .pop .meta { color:var(--mut); font-size:11px; margin:3px 0 8px; }
  .pop button { margin-right:6px; padding:6px 10px; border-radius:4px; font-size:12px;
    border:1px solid var(--line); background:transparent; color:var(--tx); cursor:pointer; }
  .hint { position:fixed; top:64px; left:50%; transform:translateX(-50%);
          background:var(--blue); color:#04121f; font-size:12.5px; font-weight:700;
          padding:7px 14px; border-radius:999px; z-index:1000; display:none; }
</style></head>
<body>
<header>
  <h1>⛪ 전도 지도</h1>
  <nav>
    <button id="addBtn" class="navbtn" onclick="toggleAdd()">＋ 지점 추가</button>
    <button class="navbtn" onclick="locate()">◎ 내 위치</button>
    <a href="/console">콘솔</a>
  </nav>
</header>
<div id="hint" class="hint">지도를 탭하면 지점이 추가됩니다</div>
<div id="map"></div>
<div class="stats">
  <span>완료 <b class="d" id="cntDone">0</b></span>
  <span>예정 <b class="t" id="cntTodo">0</b></span>
  <span>전체 <b id="cntAll">0</b></span>
</div>
<script>
const map = L.map('map').setView([37.5665, 126.9780], 14);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(map);

let spots = [], layer = L.layerGroup().addTo(map), addMode = false;

async function api(payload) {
  let r;
  try {
    r = await fetch('/api/mission', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload) });
  } catch(e) { alert('네트워크 오류: ' + e.message); return null; }
  const d = await r.json();
  if (!r.ok || !d.spots) { alert(d.message || '저장 실패'); return null; }
  return d;
}
function icon(status) {
  const c = status === 'done' ? '#00C077' : '#F5A623';
  return L.divIcon({ className:'', iconSize:[22,22], iconAnchor:[11,11],
    html:`<div style="width:20px;height:20px;border-radius:50%;background:${c};
      border:2.5px solid #0A0E14; box-shadow:0 0 6px ${c}"></div>` });
}
function render() {
  layer.clearLayers();
  let d=0, t=0;
  spots.forEach(s => {
    s.status === 'done' ? d++ : t++;
    const m = L.marker([s.lat, s.lng], { icon: icon(s.status) }).addTo(layer);
    m._sid = s.id;
    m.bindPopup(`<div class="pop"><b>${s.name}</b>
      <div class="meta">${s.status==='done'?'전도 완료':'방문 예정'} · ${s.time}</div>
      <button onclick="toggle('${s.id}')">${s.status==='done'?'예정으로':'완료로'}</button>
      <button onclick="removeSpot('${s.id}')">삭제</button></div>`);
  });
  document.getElementById('cntDone').textContent = d;
  document.getElementById('cntTodo').textContent = t;
  document.getElementById('cntAll').textContent = spots.length;
}
async function load() {
  const r = await fetch('/api/mission');
  spots = (await r.json()).spots || [];
  render();
  if (spots.length) map.fitBounds(spots.map(s=>[s.lat,s.lng]), {padding:[40,40], maxZoom:16});
}
function toggleAdd() {
  addMode = !addMode;
  document.getElementById('addBtn').classList.toggle('on', addMode);
  document.getElementById('hint').style.display = addMode ? 'block' : 'none';
}
map.on('click', async e => {
  if (!addMode) return;
  const name = prompt('지점 이름 (예: OO아파트 3단지, OO상가)');
  if (!name) return;
  const done = confirm('이미 전도를 완료한 곳인가요?\\n확인=완료 · 취소=방문 예정');
  const r = await api({ action:'add', lat:e.latlng.lat, lng:e.latlng.lng,
                        name, status: done ? 'done' : 'todo' });
  if (r) {
    spots = r.spots; render(); toggleAdd();
    const added = r.spots[r.spots.length - 1];
    map.panTo([added.lat, added.lng]);
    layer.eachLayer(m => { if (m._sid === added.id) m.openPopup(); });
  }
});
async function toggle(id) {
  const r = await api({ action:'toggle', id });
  if (r) { spots = r.spots; render(); }
}
async function removeSpot(id) {
  if (!confirm('이 지점을 삭제할까요?')) return;
  const r = await api({ action:'delete', id });
  if (r) { spots = r.spots; render(); }
}
let locLayer = L.layerGroup().addTo(map);
function locate() {
  if (!navigator.geolocation) { alert('이 브라우저는 위치 기능을 지원하지 않습니다'); return; }
  const btn = document.querySelector('.navbtn:nth-child(2)');
  btn.textContent = '위치 찾는 중…';
  navigator.geolocation.getCurrentPosition(
    pos => {
      btn.textContent = '◎ 내 위치';
      const ll = [pos.coords.latitude, pos.coords.longitude];
      locLayer.clearLayers();
      L.circle(ll, { radius: Math.min(pos.coords.accuracy, 150),
        color:'#3E9DFF', weight:1, fillOpacity:.15 }).addTo(locLayer);
      L.circleMarker(ll, { radius:7, color:'#0A0E14', weight:2,
        fillColor:'#3E9DFF', fillOpacity:1 }).addTo(locLayer);
      map.setView(ll, 16);
    },
    err => {
      btn.textContent = '◎ 내 위치';
      if (err.code === 1)
        alert('위치 권한이 거부되어 있습니다. 아이폰: 설정 > 개인정보 보호 > 위치 서비스 > Safari 웹사이트 = "앱을 사용하는 동안"으로 켠 뒤, Safari 주소창 왼쪽 ㅁA > 웹 사이트 설정 > 위치 = 허용으로 변경하세요.');
      else if (err.code === 3) alert('위치를 가져오는 데 시간이 초과됐습니다. 실외에서 다시 시도해보세요.');
      else alert('위치를 가져올 수 없습니다: ' + err.message);
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
}
load();
setInterval(async () => {
  try {
    const r = await fetch('/api/mission');
    const d = await r.json();
    const cur = JSON.stringify(spots), nw = JSON.stringify(d.spots || []);
    if (cur !== nw) { spots = d.spots || []; render(); }
  } catch(e) {}
}, 12000);
</script>
</body></html>"""
