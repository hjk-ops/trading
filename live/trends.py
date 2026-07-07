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


TRENDS_PAGE = r"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>\U0001F525 트렌드</title>
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
            letter-spacing:.12em; color:var(--mut); margin:0 0 10px;
            display:flex; justify-content:space-between; }
  .vids { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
  .vid { background:var(--panel); border:1px solid var(--line); border-radius:8px;
         overflow:hidden; text-decoration:none; color:var(--tx); position:relative; }
  .vid img { width:100%; display:block; aspect-ratio:16/9; object-fit:cover; background:#000; }
  .vid .t { font-size:12px; line-height:1.4; padding:8px 10px 2px;
            display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .vid .m { font-size:10.5px; color:var(--mut); padding:2px 10px 10px;
            font-family:'IBM Plex Mono',monospace; }
  .tab { font-family:'IBM Plex Mono',monospace; font-size:10.5px; padding:4px 10px;
         border:1px solid var(--line); border-radius:3px; background:transparent;
         color:var(--mut); cursor:pointer; margin-left:4px; }
  .tab.on { border-color:var(--hot); color:var(--hot); }
  .note { color:var(--mut); font-size:11px; padding:0 16px 24px;
          font-family:'IBM Plex Mono',monospace; line-height:1.6; }
  .load { color:var(--mut); font-size:12px; padding:20px; text-align:center; }
</style></head>
<body>
<header><h1>\U0001F525 실시간 트렌드</h1><a href="/">콘솔</a></header>
<div class="sec">
  <h2>YOUTUBE 최신 인기 채널 영상
    <span><button class="tab on" data-f="all">전체</button>
      <button class="tab" data-f="shorts">쇼츠만</button></span></h2>
  <div class="vids" id="vids"><div class="load">불러오는 중\u2026</div></div>
</div>
<p class="note" id="note"></p>
<script>
const CHANNELS = [
  ['UCUj6rrhMTR9pipbAWBAMvUQ','\uCE68\uCC29\uB9E8'],
  ['UCsJ6RuBiTVWRX156FVbeaGg','\uC790\uC774\uC5B8\uD2B8'],
  ['UCwEcXSGwyaVfssKGkMFvfKw','\uC544\uC774\uC2A4\uD06C\uB9BC'],
  ['UC5BMQOsAB8hKUyHu9KI6yig','\uC194\uB960'],
  ['UCaf3rIWFQTFo1LEmpXtWlmw','\uD478\uC99DTV'],
  ['UCcQTRi69dsVYHN3exePtZ1A','\uAE40\uACC4\uB780'],
  ['UCX3Ecp2v9Ss73xxNZorHb2A','\uACFC\uD559\uCFE0\uD0A4'],
  ['UChfnMcjJc0EA_dbwXbWnAbA','\uBCA4\uD2B8\uC5B4TV']
];
let all = [], filter = 'all';
const PROXY = 'https://api.allorigins.win/raw?url=';
function isShort(u){ return /\/shorts\//.test(u); }
async function fetchChannel([id, name]) {
  const rss = 'https://www.youtube.com/feeds/videos.xml?channel_id=' + id;
  for (const u of [rss, PROXY + encodeURIComponent(rss)]) {
    try {
      const r = await fetch(u); if (!r.ok) continue;
      const xml = new DOMParser().parseFromString(await r.text(), 'text/xml');
      return [...xml.querySelectorAll('entry')].slice(0,4).map(e => {
        const link = e.querySelector('link')?.getAttribute('href') || '';
        const vid = (e.getElementsByTagName('yt:videoId')[0]?.textContent)
                 || link.split('v=')[1];
        return { id: vid, title: e.querySelector('title')?.textContent || '',
                 channel: name, ts: e.querySelector('published')?.textContent || '',
                 shorts: isShort(link) };
      }).filter(v => v.id);
    } catch(e) {}
  }
  return [];
}
function timeAgo(iso){ const d=(Date.now()-new Date(iso))/86400000;
  return d<1 ? Math.round(d*24)+'\uC2DC\uAC04 \uC804' : Math.round(d)+'\uC77C \uC804'; }
function render() {
  const list = all.filter(v => filter==='all' || v.shorts)
    .sort((a,b)=>(b.ts||'').localeCompare(a.ts||'')).slice(0,30);
  document.getElementById('vids').innerHTML = list.map(v => {
    const url = v.shorts ? 'https://www.youtube.com/shorts/'+v.id
                         : 'https://www.youtube.com/watch?v='+v.id;
    const ago = v.ts ? timeAgo(v.ts) : '';
    return '<a class="vid" target="_blank" href="'+url+'">'+
      (v.shorts?'<span style="position:absolute;top:6px;left:6px;background:#FF4D5Ecc;color:#fff;font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px">SHORTS</span>':'')+
      '<img loading="lazy" src="https://i.ytimg.com/vi/'+v.id+'/mqdefault.jpg">'+
      '<div class="t">'+v.title+'</div>'+
      '<div class="m">'+v.channel+(ago?' \u00B7 '+ago:'')+'</div></a>';
  }).join('') || '<div class="load">\uD574\uB2F9 \uD56D\uBAA9 \uC5C6\uC74C</div>';
}
document.addEventListener('click', e => {
  const b = e.target.closest('.tab'); if(!b) return;
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); filter=b.dataset.f; render();
});
async function load() {
  const res = await Promise.all(CHANNELS.map(fetchChannel));
  all = res.flat();
  document.getElementById('note').textContent = all.length
    ? '\uD604\uC7AC \uAE30\uAE30\uC5D0\uC11C \uC9C1\uC811 \uC218\uC9D1 \u00B7 \uC778\uAE30 \uCC44\uB110 RSS \u00B7 5\uBD84\uB9C8\uB2E4 \uAC31\uC2E0'
    : '';
  if (all.length) render();
  else document.getElementById('vids').innerHTML =
    '<div class="load">\uBD88\uB7EC\uC624\uC9C0 \uBABB\uD588\uC5B4\uC694. \uC7A0\uC2DC \uD6C4 \uC0C8\uB85C\uACE0\uCE68\uD574\uC8FC\uC138\uC694.</div>';
}
load(); setInterval(load, 300000);
</script>
</body></html>"""
