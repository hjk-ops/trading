"""🔥 트렌드 메뉴: API 키 없이 공개 소스에서 수집.

- Google Trends KR RSS (공식 피드)
- YouTube 인기 급상승 페이지 파싱 (비공식 — 구조 변경 시 깨질 수 있음)
10분 캐시. 실패 시 마지막 성공 데이터 유지.
"""
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

_CACHE = {"t": 0, "data": None}
_UA = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                     "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile Safari/604.1",
       "Accept-Language": "ko-KR,ko;q=0.9"}


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers=_UA)
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def _google_trends():
    xml = _get("https://trends.google.com/trending/rss?geo=KR")
    root = ET.fromstring(xml)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    out = []
    for item in root.iter("item"):
        title = item.findtext("title", "")
        traffic = item.findtext("ht:approx_traffic", "", ns)
        if title:
            out.append({"title": title, "traffic": traffic})
    return out[:20]


def _walk(node, key, acc):
    if isinstance(node, dict):
        if key in node:
            acc.append(node[key])
        for v in node.values():
            _walk(v, key, acc)
    elif isinstance(node, list):
        for v in node:
            _walk(v, key, acc)


def _youtube_trending():
    html = _get("https://www.youtube.com/feed/trending?gl=KR&hl=ko")
    m = re.search(r"var ytInitialData = ({.*?});</script>", html, re.S)
    if not m:
        m = re.search(r'window\["ytInitialData"\] = ({.*?});', html, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    vids, out, seen = [], [], set()
    _walk(data, "videoRenderer", vids)
    for v in vids:
        vid = v.get("videoId")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        title = "".join(r.get("text", "") for r in v.get("title", {}).get("runs", []))
        views = v.get("viewCountText", {}).get("simpleText", "")
        ch = "".join(r.get("text", "") for r in
                     v.get("ownerText", {}).get("runs", []))
        length = v.get("lengthText", {}).get("simpleText", "")
        out.append({"id": vid, "title": title[:80], "views": views,
                    "channel": ch, "len": length, "shorts": _is_short(length)})
        if len(out) >= 40:
            break
    # 쇼츠 전용 렌더러(reelItemRenderer)도 수집
    reels = []
    _walk(data, "reelItemRenderer", reels)
    for v in reels:
        vid = v.get("videoId")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        title = v.get("headline", {}).get("simpleText", "")
        views = v.get("viewCountText", {}).get("simpleText", "")
        out.append({"id": vid, "title": title[:80], "views": views,
                    "channel": "", "len": "쇼츠", "shorts": True})
    return out


def _is_short(length_text):
    """'0:45' 같은 길이 문자열이 60초 이하인지."""
    try:
        parts = [int(x) for x in length_text.split(":")]
        sec = parts[-1] + (parts[-2] * 60 if len(parts) > 1 else 0) \
              + (parts[-3] * 3600 if len(parts) > 2 else 0)
        return sec <= 61
    except Exception:
        return False


def fetch_trends():
    now = time.time()
    if _CACHE["data"] and now - _CACHE["t"] < 600:
        return _CACHE["data"]
    if os.environ.get("FAKE_TRENDS"):
        data = {"google": [{"title": f"테스트 검색어 {i}", "traffic": f"{i}0만+"} for i in range(1, 6)],
                "youtube": [{"id": "dQw4w9WgXcQ", "title": f"테스트 영상 {i}", "views": "123만회",
                             "channel": "채널", "len": "0:45" if i % 2 else "5:30",
                             "shorts": bool(i % 2)} for i in range(1, 5)],
                "updated": time.strftime("%H:%M")}
        _CACHE.update(t=now, data=data)
        return data
    data = {"google": [], "youtube": [], "updated": time.strftime("%H:%M")}
    try:
        data["google"] = _google_trends()
    except Exception:
        pass
    try:
        data["youtube"] = _youtube_trending()
    except Exception:
        pass
    if data["google"] or data["youtube"]:
        _CACHE.update(t=now, data=data)
        return data
    return _CACHE["data"] or data


TRENDS_PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🔥 트렌드</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0A0E14; --panel:#11161F; --line:#1E2530; --tx:#D7DEE8;
          --mut:#6B7686; --hot:#FF4D5E; --blue:#3E9DFF; }
  body { font-family:'IBM Plex Sans KR',sans-serif; background:var(--bg);
         color:var(--tx); margin:0; font-size:14px; }
  header { display:flex; align-items:center; gap:10px; padding:12px 16px;
           background:var(--panel); border-bottom:1px solid var(--line); }
  header h1 { font-size:14px; font-weight:700; letter-spacing:.08em; margin:0; }
  header a { margin-left:auto; font-size:12px; color:var(--mut); text-decoration:none;
             border:1px solid var(--line); padding:5px 10px; border-radius:4px; }
  .sec { margin:14px 16px; }
  .sec h2 { font-family:'IBM Plex Mono',monospace; font-size:11px;
            letter-spacing:.12em; color:var(--mut); margin:0 0 10px; }
  .chips { display:flex; flex-wrap:wrap; gap:8px; }
  .chip { background:var(--panel); border:1px solid var(--line); border-radius:999px;
          padding:8px 14px; font-size:13px; color:var(--tx); text-decoration:none; }
  .chip b { color:var(--hot); font-weight:700; margin-right:6px; }
  .chip span { color:var(--mut); font-size:11px; margin-left:6px; }
  .vids { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .vid { background:var(--panel); border:1px solid var(--line); border-radius:8px;
         overflow:hidden; text-decoration:none; color:var(--tx); }
  .vid img { width:100%; display:block; aspect-ratio:16/9; object-fit:cover; }
  .vid .t { font-size:12px; line-height:1.4; padding:8px 10px 2px;
            display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .vid .m { font-size:10.5px; color:var(--mut); padding:2px 10px 10px;
            font-family:'IBM Plex Mono',monospace; }
  .badge { position:absolute; }
  .tab { font-family:'IBM Plex Mono',monospace; font-size:10.5px; padding:4px 10px;
         border:1px solid var(--line); border-radius:3px; background:transparent;
         color:var(--mut); cursor:pointer; margin-left:4px; }
  .tab.on { border-color:var(--hot); color:var(--hot); }
  .shortsBadge { position:absolute; top:6px; left:6px; background:#FF4D5Ecc; color:#fff;
         font-size:9px; font-weight:700; padding:2px 6px; border-radius:3px; }
  .vid { position:relative; }
  .muted { color:var(--mut); font-size:11px; padding:0 16px 24px;
           font-family:'IBM Plex Mono',monospace; }
</style></head>
<body>
<header>
  <h1>🔥 실시간 트렌드</h1>
  <a href="/">콘솔</a>
</header>
<div class="sec">
  <h2>GOOGLE 실시간 인기 검색어 · KR</h2>
  <div class="chips" id="chips">불러오는 중…</div>
</div>
<div class="sec">
  <h2>YOUTUBE 인기 급상승 · KR
    <span style="float:right">
      <button class="tab on" data-f="all">전체</button>
      <button class="tab" data-f="shorts">쇼츠만</button>
    </span></h2>
  <div class="vids" id="vids"></div>
</div>
<p class="muted" id="upd">10분 주기 갱신</p>
<script>
let filter = 'all', cache = null;
document.addEventListener('click', e => {
  const b = e.target.closest('.tab'); if (!b) return;
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); filter = b.dataset.f; renderVids();
});
function renderVids() {
  const list = (cache && cache.youtube || [])
    .filter(v => filter === 'all' || v.shorts);
  document.getElementById('vids').innerHTML = list.map(v => {
    const url = v.shorts ? `https://www.youtube.com/shorts/${v.id}`
                         : `https://www.youtube.com/watch?v=${v.id}`;
    return `<a class="vid" target="_blank" href="${url}">
      ${v.shorts ? '<span class="shortsBadge">SHORTS</span>' : ''}
      <img loading="lazy" src="https://i.ytimg.com/vi/${v.id}/mqdefault.jpg">
      <div class="t">${v.title}</div>
      <div class="m">${v.channel || ''} ${v.views || ''}${v.len && v.len !== '쇼츠' ? ' · ' + v.len : ''}</div></a>`;
  }).join('') || '<span style="color:#6B7686">해당 항목 없음</span>';
}
async function load() {
  const r = await fetch('/api/trends');
  const d = await r.json();
  document.getElementById('chips').innerHTML = (d.google || []).map((g, i) =>
    `<a class="chip" target="_blank"
        href="https://www.google.com/search?q=${encodeURIComponent(g.title)}">
        <b>${i+1}</b>${g.title}${g.traffic ? `<span>${g.traffic}</span>` : ''}</a>`
  ).join('') || '<span style="color:#6B7686">데이터 없음 (잠시 후 갱신)</span>';
  cache = d; renderVids();
  document.getElementById('upd').textContent =
    `마지막 수집 ${d.updated || '-'} · 10분 주기 갱신 · 출처: Google Trends RSS, YouTube 인기`;
}
load(); setInterval(load, 120000);
</script>
</body></html>"""
