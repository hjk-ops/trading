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
<script src="https://dapi.kakao.com/v2/maps/sdk.js?appkey=__KAKAO_KEY__&autoload=false"></script>
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
  .stats b.d { color:var(--done); } .stats b.t { color:var(--todo); } .stats b.p { color:var(--blue); }
  .sheet { position:fixed; inset:0; background:#0009; z-index:3000; display:flex;
           align-items:flex-end; }
  .sheet .box { background:var(--panel); border-top:1px solid var(--line);
                border-radius:16px 16px 0 0; width:100%; padding:16px 16px 26px; }
  .sheet h3 { font-size:14px; margin:0 0 12px; }
  .sheet button { display:block; width:100%; margin:8px 0; padding:14px;
                  font-size:15px; font-weight:700; border-radius:10px; border:1px solid var(--line);
                  background:var(--bg); color:var(--tx); }
  .sheet .sd { border-color:var(--done); color:var(--done); }
  .sheet .st { border-color:var(--todo); color:var(--todo); }
  .sheet .sp { border-color:var(--blue); color:var(--blue); }
  .kpop { background:var(--panel); color:var(--tx); border:1px solid var(--line);
    border-radius:10px; padding:12px 14px; min-width:190px;
    box-shadow:0 8px 28px #000a; transform:translate(-50%, calc(-100% - 16px)); }
  .kpop:after { content:''; position:absolute; left:50%; bottom:-7px; margin-left:-7px;
    width:12px; height:12px; background:var(--panel); border-right:1px solid var(--line);
    border-bottom:1px solid var(--line); transform:rotate(45deg); }
  .pop b { font-size:14px; }
  .pop .meta { color:var(--mut); font-size:11px; margin:3px 0 8px; }
  .pop button { margin-right:6px; padding:6px 10px; border-radius:4px; font-size:12px;
    border:1px solid var(--line); background:transparent; color:var(--tx); cursor:pointer; }
  .toast { position:fixed; top:64px; left:12px; right:12px; z-index:2000;
           background:var(--panel); border:1px solid var(--todo); border-radius:10px;
           padding:12px 14px; font-size:13px; line-height:1.55; color:var(--tx);
           box-shadow:0 6px 24px #0009; }
  .toast .x { float:right; color:var(--mut); font-size:16px; padding:0 4px; }
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
  </nav>
</header>
<div id="hint" class="hint">지도를 탭하면 지점이 추가됩니다</div>
<div id="map"></div>
<div class="stats">
  <span>완료 <b class="d" id="cntDone">0</b></span>
  <span>예정 <b class="t" id="cntTodo">0</b></span>
  <span>픽업 <b class="p" id="cntPickup">0</b></span>
  <span>전체 <b id="cntAll">0</b></span>
</div>
<script>
let map, overlays = [], popOverlay = null, addMode = false, spots = [], locOv = null;
let toastEl = null;
function toast(html) {
  if (toastEl) toastEl.remove();
  toastEl = document.createElement('div');
  toastEl.className = 'toast';
  toastEl.innerHTML = '<span class="x">✕</span>' + html;
  toastEl.onclick = () => { toastEl.remove(); toastEl = null; };
  document.body.appendChild(toastEl);
  setTimeout(() => { if (toastEl) { toastEl.remove(); toastEl = null; } }, 12000);
}
if (typeof kakao === 'undefined') {
  document.getElementById('map').innerHTML =
    '<div style="padding:40px 20px;text-align:center;color:#6B7686">지도를 불러오지 못했어요.<br>카카오 개발자 콘솔에서 JS SDK 도메인에<br><b style="color:#D7DEE8">이 사이트 주소</b>가 등록됐는지 확인해주세요.</div>';
} else kakao.maps.load(init);

const STATUS_META = { done:['전도 완료','#00C077'], todo:['방문 예정','#F5A623'],
                      pickup:['픽업 필요','#3E9DFF'] };

function init() {
  map = new kakao.maps.Map(document.getElementById('map'),
    { center: new kakao.maps.LatLng(37.5665, 126.9780), level: 4 });
  kakao.maps.event.addListener(map, 'click', e => {
    if (popOverlay) { popOverlay.setMap(null); popOverlay = null; return; }
    if (addMode) onAdd(e.latLng.getLat(), e.latLng.getLng());
  });
  load();
  setInterval(sync, 12000);
}
function dot(status) {
  const c = (STATUS_META[status] || STATUS_META.todo)[1];
  const el = document.createElement('div');
  el.style.cssText = `width:20px;height:20px;border-radius:50%;background:${c};
    border:2.5px solid #0A0E14;box-shadow:0 0 6px ${c};cursor:pointer`;
  return el;
}
function render() {
  overlays.forEach(o => o.setMap(null)); overlays = [];
  const cnt = { done:0, todo:0, pickup:0 };
  spots.forEach(s => {
    cnt[s.status] = (cnt[s.status]||0) + 1;
    const el = dot(s.status);
    const ov = new kakao.maps.CustomOverlay({
      position: new kakao.maps.LatLng(s.lat, s.lng), content: el, yAnchor: 0.5 });
    ov.setMap(map);
    el.onclick = ev => { ev.stopPropagation(); openPop(s); };
    overlays.push(ov);
  });
  document.getElementById('cntDone').textContent = cnt.done;
  document.getElementById('cntTodo').textContent = cnt.todo;
  document.getElementById('cntPickup').textContent = cnt.pickup;
  document.getElementById('cntAll').textContent = spots.length;
}
function openPop(s) {
  if (popOverlay) popOverlay.setMap(null);
  const meta = STATUS_META[s.status] || STATUS_META.todo;
  const el = document.createElement('div');
  el.className = 'kpop';
  el.innerHTML = `<b>${s.name}</b>
    <div class="meta" style="color:${meta[1]};font-size:11px;margin:3px 0 8px">● ${meta[0]} · ${s.time}</div>`;
  Object.entries(STATUS_META).filter(([k]) => k !== s.status).forEach(([k,[label,c]]) => {
    const b = document.createElement('button');
    b.textContent = label;
    b.style.cssText = `margin:0 6px 6px 0;padding:6px 10px;border-radius:4px;font-size:12px;
      border:1px solid ${c};color:${c};background:transparent`;
    b.onclick = () => setStatus(s.id, k);
    el.appendChild(b);
  });
  const del = document.createElement('button');
  del.textContent = '삭제';
  del.style.cssText = 'padding:6px 10px;border-radius:4px;font-size:12px;border:1px solid #2A3342;color:#6B7686;background:transparent';
  del.onclick = () => removeSpot(s.id);
  el.appendChild(del);
  popOverlay = new kakao.maps.CustomOverlay({
    position: new kakao.maps.LatLng(s.lat, s.lng), content: el, yAnchor: 0, zIndex: 10 });
  popOverlay.setMap(map);
}
async function api(payload) {
  let r;
  try {
    r = await fetch('/api/mission', { method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload) });
  } catch(e) { toast('네트워크 오류: ' + e.message); return null; }
  const d = await r.json();
  if (!r.ok || !d.spots) { toast(d.message || '저장 실패'); return null; }
  return d;
}
async function load() {
  const r = await fetch('/api/mission');
  spots = (await r.json()).spots || [];
  render();
  if (spots.length) {
    const b = new kakao.maps.LatLngBounds();
    spots.forEach(s => b.extend(new kakao.maps.LatLng(s.lat, s.lng)));
    map.setBounds(b, 60);
  }
}
async function sync() {
  try {
    const r = await fetch('/api/mission');
    const d = await r.json();
    if (JSON.stringify(spots) !== JSON.stringify(d.spots || [])) {
      spots = d.spots || []; render();
    }
  } catch(e) {}
}
function toggleAdd() {
  addMode = !addMode;
  document.getElementById('addBtn').classList.toggle('on', addMode);
  document.getElementById('hint').style.display = addMode ? 'block' : 'none';
}
function pickStatus(name) {
  return new Promise(res => {
    const el = document.createElement('div');
    el.className = 'sheet';
    el.innerHTML = `<div class="box"><h3>"${name}" 상태 선택</h3>
      <button class="sd">✔ 전도 완료</button>
      <button class="st">◷ 방문 예정</button>
      <button class="sp">📦 픽업 필요</button>
      <button>취소</button></div>`;
    const [bd, bt, bp, bc] = el.querySelectorAll('button');
    bd.onclick = () => { el.remove(); res('done'); };
    bt.onclick = () => { el.remove(); res('todo'); };
    bp.onclick = () => { el.remove(); res('pickup'); };
    bc.onclick = () => { el.remove(); res(null); };
    document.body.appendChild(el);
  });
}
async function onAdd(lat, lng) {
  const name = prompt('지점 이름 (예: OO아파트 3단지, OO상가)');
  if (!name) return;
  const status = await pickStatus(name);
  if (!status) return;
  const r = await api({ action:'add', lat, lng, name, status });
  if (r) {
    spots = r.spots; render(); toggleAdd();
    const added = r.spots[r.spots.length - 1];
    map.panTo(new kakao.maps.LatLng(added.lat, added.lng));
    openPop(added);
  }
}
async function setStatus(id, status) {
  const r = await api({ action:'status', id, status });
  if (r) { spots = r.spots; render();
    const s = r.spots.find(x=>x.id===id); if (s) openPop(s); }
}
async function removeSpot(id) {
  if (!confirm('이 지점을 삭제할까요?')) return;
  const r = await api({ action:'delete', id });
  if (r) { spots = r.spots; render();
    if (popOverlay) { popOverlay.setMap(null); popOverlay = null; } }
}
function locate() {
  if (!navigator.geolocation) { toast('이 브라우저는 위치 기능을 지원하지 않습니다'); return; }
  const btn = document.querySelector('.navbtn:nth-child(2)');
  btn.textContent = '위치 찾는 중…';
  navigator.geolocation.getCurrentPosition(
    pos => {
      btn.textContent = '◎ 내 위치';
      const ll = new kakao.maps.LatLng(pos.coords.latitude, pos.coords.longitude);
      if (locOv) locOv.setMap(null);
      const el = document.createElement('div');
      el.style.cssText = 'width:16px;height:16px;border-radius:50%;background:#3E9DFF;border:3px solid #0A0E14;box-shadow:0 0 10px #3E9DFF';
      locOv = new kakao.maps.CustomOverlay({ position: ll, content: el, yAnchor: 0.5 });
      locOv.setMap(map);
      map.setLevel(3); map.panTo(ll);
    },
    err => {
      btn.textContent = '◎ 내 위치';
      if (err.code === 1)
        toast('위치 권한이 꺼져 있어요. <b>주소창 왼쪽 ㅁA → 웹 사이트 설정 → 위치 → 허용</b>으로 바꾸고 다시 눌러주세요.');
      else if (err.code === 3) toast('위치 잡기에 시간이 걸리네요. 실외에서 다시 시도해보세요.');
      else toast('위치를 가져올 수 없어요: ' + err.message);
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 });
}
</script>
</body></html>"""
