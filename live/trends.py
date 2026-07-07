"""🔥 트렌드 메뉴.

수집 방식:
- Google Trends KR: 공식 RSS (안정적)
- YouTube 인기급상승: Innertube API (YouTube 내부 API, 앱 동일 방식)
  → 일반 크롤링과 달리 차단이 훨씬 적음
- Instagram/TikTok: 서버에서 수집 불가 (로그인 필수 + 강력 차단)
  → 클라이언트 임베드 위젯으로 대체

10분 캐시. 소스별 실패 독립 처리 (하나 깨져도 다른 건 표시).
"""
import json
import os
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

_CACHE = {"t": 0, "data": None}

_UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# ── Google Trends RSS ──────────────────────────────────────────────
def _google_trends():
    req = urllib.request.Request(
        "https://trends.google.com/trending/rss?geo=KR",
        headers={"User-Agent": _UA_BROWSER, "Accept-Language": "ko-KR,ko;q=0.9"})
    xml = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
    root = ET.fromstring(xml)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        traffic = item.findtext("ht:approx_traffic", "", ns)
        if title:
            out.append({"title": title, "traffic": traffic,
                        "url": f"https://www.google.com/search?q={urllib.parse.quote(title)}"})
    return out[:20]

# ── YouTube Innertube API ──────────────────────────────────────────
_INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
_INNERTUBE_URL = f"https://www.youtube.com/youtubei/v1/browse?key={_INNERTUBE_KEY}&prettyPrint=false"

def _innertube_ctx():
    return {"context": {"client": {
        "clientName": "WEB", "clientVersion": "2.20240101.00.00",
        "gl": "KR", "hl": "ko",
        "userAgent": _UA_BROWSER + ",gzip(gfe)",
        "timeZone": "Asia/Seoul",
    }}}

def _walk(node, key, acc, limit=60):
    if len(acc) >= limit: return
    if isinstance(node, dict):
        if key in node: acc.append(node[key])
        for v in node.values(): _walk(v, key, acc, limit)
    elif isinstance(node, list):
        for v in node: _walk(v, key, acc, limit)

def _sec_to_txt(s):
    s = int(s)
    return f"{s//60}:{s%60:02d}"

def _youtube_trending():
    body = {**_innertube_ctx(), "browseId": "FEtrending",
            "params": "4gINGgt5dG1hX2NoYXJ0cw%3D%3D"}  # trending charts
    req = urllib.request.Request(
        _INNERTUBE_URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": _UA_BROWSER,
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": "2.20240101.00.00",
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/feed/trending",
        })
    data = json.loads(urllib.request.urlopen(req, timeout=15).read())
    vids, out, seen = [], [], set()
    _walk(data, "videoRenderer", vids, 60)
    _walk(data, "reelItemRenderer", vids, 60)
    for v in vids:
        vid = v.get("videoId")
        if not vid or vid in seen: continue
        seen.add(vid)
        title = "".join(r.get("text","") for r in v.get("title",{}).get("runs", []))
        if not title: title = v.get("headline",{}).get("simpleText","")
        views = (v.get("viewCountText",{}).get("simpleText","") or
                 v.get("viewCountText",{}).get("runs",[{}])[0].get("text",""))
        ch = "".join(r.get("text","") for r in v.get("ownerText",{}).get("runs",[]))
        length = v.get("lengthText",{}).get("simpleText","")
        is_short = False
        try:
            parts = [int(x) for x in length.split(":")]
            sec = parts[-1] + (parts[-2]*60 if len(parts)>1 else 0)
            is_short = sec <= 61
        except: pass
        out.append({"id": vid, "title": title[:80], "views": views,
                    "channel": ch, "len": length, "shorts": is_short})
        if len(out) >= 30: break
    return out

# ── 인기 유튜버 최신 영상 (채널 RSS, 급상승 보완용) ────────────────
_KR_CHANNELS = [
    ("침착맨", "UC9lNg87GkXoaGGqY83vPM7w"),
    ("피식대학", "UCMOHEBTmkSYH7tXmrHWlTMQ"),
    ("스우파2", "UC94BDKRfBvXIFZdUZDRK08g"),
    ("동네한바퀴", "UCTRXpEb3fZZTMf_yE9cB-sQ"),
    ("KBS뉴스", "UCcQTRi69dsVYHN3exePtZ1A"),
    ("MBC뉴스", "UCF5P4pO0-U9UIQFB-TkiUng"),
]

def _channel_rss():
    ns = {"a": "http://www.w3.org/2005/Atom",
          "yt": "http://www.youtube.com/xml/schemas/2015"}
    out = []
    for ch_name, cid in _KR_CHANNELS:
        try:
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
            req = urllib.request.Request(url, headers={"User-Agent": _UA_BROWSER})
            xml = urllib.request.urlopen(req, timeout=8).read()
            root = ET.fromstring(xml)
            for e in root.findall("a:entry", ns)[:2]:
                vid = e.findtext("yt:videoId", ns=ns, default="")
                title = e.findtext("a:title", ns=ns, default="")
                if vid and title:
                    out.append({"id": vid, "title": title[:80], "views": "",
                                "channel": ch_name, "len": "", "shorts": False})
        except: pass
    return out

# ── 메인 수집 ──────────────────────────────────────────────────────
def fetch_trends():
    now = time.time()
    if _CACHE["data"] and now - _CACHE["t"] < 600:
        return _CACHE["data"]
    if os.environ.get("FAKE_TRENDS"):
        data = {
            "google": [{"title": f"테스트 검색어 {i}", "traffic": f"{i}0만+",
                        "url": "#"} for i in range(1,6)],
            "youtube": [{"id": "dQw4w9WgXcQ", "title": f"테스트 영상 {i}",
                         "views": f"{i}23만회", "channel": "채널", "len": "3:30",
                         "shorts": bool(i%2)} for i in range(1,8)],
            "updated": time.strftime("%H:%M"), "errors": {},
        }
        _CACHE.update(t=now, data=data); return data

    data = {"google": [], "youtube": [], "updated": time.strftime("%H:%M"), "errors": {}}
    # Google Trends
    try:
        data["google"] = _google_trends()
    except Exception as e:
        data["errors"]["google"] = str(e)[:80]
    # YouTube Innertube
    try:
        yt = _youtube_trending()
        data["youtube"] = yt
    except Exception as e:
        data["errors"]["youtube_innertube"] = str(e)[:80]
        # Innertube 실패 시 채널 RSS 폴백
        try:
            data["youtube"] = _channel_rss()
            if data["youtube"]: data["errors"].pop("youtube_innertube", None)
        except Exception as e2:
            data["errors"]["youtube_rss"] = str(e2)[:80]

    if data["google"] or data["youtube"]:
        _CACHE.update(t=now, data=data)
    else:
        _CACHE.update(t=now-480, data=_CACHE.get("data") or data)
    return _CACHE["data"]


TRENDS_PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🔥 트렌드</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0A0E14; --panel:#11161F; --line:#1E2530; --tx:#D7DEE8;
          --mut:#6B7686; --hot:#FF4D5E; --blue:#3E9DFF; --ok:#00C077; }
  body { font-family:'IBM Plex Sans KR',sans-serif; background:var(--bg);
         color:var(--tx); margin:0; font-size:14px; }
  header { display:flex; align-items:center; gap:10px; padding:12px 16px;
           background:var(--panel); border-bottom:1px solid var(--line); }
  header h1 { font-size:14px; font-weight:700; letter-spacing:.06em; margin:0; }
  header a { margin-left:auto; font-size:12px; color:var(--mut); text-decoration:none;
             border:1px solid var(--line); padding:5px 10px; border-radius:4px; }
  .wrap { padding:14px 16px 40px; }
  .sec h2 { font-family:'IBM Plex Mono',monospace; font-size:10.5px; color:var(--mut);
             letter-spacing:.12em; margin:0 0 10px; }
  .sec { margin-bottom:20px; }
  /* 구글 트렌드 칩 */
  .chips { display:flex; flex-wrap:wrap; gap:7px; }
  .chip { background:var(--panel); border:1px solid var(--line); border-radius:999px;
          padding:8px 13px; font-size:13px; color:var(--tx); text-decoration:none;
          display:flex; align-items:center; gap:6px; }
  .chip b { color:var(--hot); font-size:12px; min-width:16px; }
  .chip span { color:var(--mut); font-size:10.5px; font-family:'IBM Plex Mono',monospace; }
  /* 유튜브 그리드 */
  .tfbar { display:flex; gap:6px; margin-bottom:10px; }
  .tf { font-family:'IBM Plex Mono',monospace; font-size:11px; padding:5px 10px;
        border:1px solid var(--line); border-radius:3px; background:transparent;
        color:var(--mut); cursor:pointer; }
  .tf.on { border-color:var(--hot); color:var(--hot); }
  .vids { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .vid { background:var(--panel); border:1px solid var(--line); border-radius:8px;
         overflow:hidden; text-decoration:none; color:var(--tx); position:relative; }
  .vid img { width:100%; display:block; aspect-ratio:16/9; object-fit:cover;
             background:#1a1d27; }
  .sbadge { position:absolute; top:6px; left:6px; background:#FF4D5Ecc; color:#fff;
            font-size:9px; font-weight:700; padding:2px 6px; border-radius:3px; }
  .vtitle { font-size:12px; line-height:1.4; padding:7px 9px 2px;
            display:-webkit-box; -webkit-line-clamp:2;
            -webkit-box-orient:vertical; overflow:hidden; }
  .vmeta { font-size:10px; color:var(--mut); padding:2px 9px 9px;
           font-family:'IBM Plex Mono',monospace; }
  /* 상태 */
  .err { color:var(--hot); font-size:11.5px; font-family:'IBM Plex Mono',monospace;
         padding:8px 0; }
  .empty { color:var(--mut); font-size:12px; text-align:center; padding:30px 0; }
  .muted { color:var(--mut); font-size:10.5px; margin-top:14px;
           font-family:'IBM Plex Mono',monospace; }
</style></head>
<body>
<header><h1>🔥 실시간 트렌드</h1><a href="/">콘솔</a></header>
<div class="wrap">

  <div class="sec">
    <h2>GOOGLE 실시간 검색어 · KR</h2>
    <div class="chips" id="chips"><span class="empty">불러오는 중…</span></div>
  </div>

  <div class="sec">
    <h2>YOUTUBE 인기 급상승 · KR
      <span style="float:right">
        <button class="tf on" data-f="all">전체</button>
        <button class="tf" data-f="shorts">쇼츠</button>
      </span>
    </h2>
    <div class="vids" id="vids"><span class="empty" style="grid-column:1/-1">불러오는 중…</span></div>
  </div>

  <p class="muted" id="foot">10분 주기 갱신</p>
</div>
<script>
let cache = null, filter = 'all';

document.querySelector('.tfbar')?.addEventListener('click', e => {
  const b = e.target.closest('.tf'); if (!b) return;
  document.querySelectorAll('.tf').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); filter = b.dataset.f; renderVids();
});
// 섹션 헤더 내 버튼 이벤트
document.querySelectorAll('.tf').forEach(b => b.addEventListener('click', e => {
  e.stopPropagation();
  document.querySelectorAll('.tf').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); filter = b.dataset.f; renderVids();
}));

function renderVids() {
  const list = (cache?.youtube || []).filter(v => filter === 'all' || v.shorts);
  const el = document.getElementById('vids');
  if (!list.length) {
    el.innerHTML = '<span class="empty" style="grid-column:1/-1">데이터 없음</span>'; return; }
  el.innerHTML = list.slice(0,24).map(v => {
    const href = v.shorts ? `https://www.youtube.com/shorts/${v.id}`
                          : `https://www.youtube.com/watch?v=${v.id}`;
    return `<a class="vid" target="_blank" rel="noopener" href="${href}">
      ${v.shorts ? '<span class="sbadge">SHORTS</span>' : ''}
      <img loading="lazy" src="https://i.ytimg.com/vi/${v.id}/mqdefault.jpg"
           onerror="this.style.display='none'">
      <div class="vtitle">${v.title}</div>
      <div class="vmeta">${v.channel||''} ${v.views||''} ${v.len||''}</div></a>`;
  }).join('');
}

async function load() {
  try {
    const r = await fetch('/api/trends');
    const d = await r.json();
    cache = d;
    // 구글
    const chips = document.getElementById('chips');
    if (d.google?.length) {
      chips.innerHTML = d.google.map((g,i) =>
        `<a class="chip" target="_blank" rel="noopener" href="${g.url}">
          <b>${i+1}</b>${g.title}${g.traffic?`<span>${g.traffic}</span>`:''}</a>`
      ).join('');
    } else {
      chips.innerHTML = `<span class="err">구글 트렌드 수집 실패: ${d.errors?.google||'알 수 없음'}</span>`;
    }
    // 유튜브
    if (d.youtube?.length) renderVids();
    else {
      const errs = [d.errors?.youtube_innertube, d.errors?.youtube_rss].filter(Boolean).join(' / ');
      document.getElementById('vids').innerHTML =
        `<span class="err" style="grid-column:1/-1">유튜브 수집 실패: ${errs||'알 수 없음'}</span>`;
    }
    document.getElementById('foot').textContent =
      `마지막 수집 ${d.updated||'-'} · 10분 주기 갱신 · 오류: ${JSON.stringify(d.errors||{})}`;
  } catch(e) {
    document.getElementById('chips').innerHTML = '<span class="err">네트워크 오류</span>';
  }
}
load(); setInterval(load, 120000);
</script>
</body></html>"""
