"""텔레그램 알림.

환경변수: TELEGRAM_TOKEN (BotFather 발급)
chat_id는 사용자가 봇에게 메시지를 한 번 보내두면 getUpdates로 자동 탐지 후
DATA_DIR/telegram_chat.json에 저장된다.

사용: from live.notify import notify; notify("메시지")
토큰이 없으면 조용히 no-op (알림 없이도 봇은 정상 동작).
"""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
CHAT_FILE = DATA_DIR / "telegram_chat.json"


def _token():
    return os.environ.get("TELEGRAM_TOKEN", "").strip()


def _api(method, params=None, timeout=6):
    tok = _token()
    if not tok:
        return None
    url = f"https://api.telegram.org/bot{tok}/{method}"
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _chat_id():
    if os.environ.get("TELEGRAM_CHAT_ID"):
        return os.environ["TELEGRAM_CHAT_ID"]
    if CHAT_FILE.exists():
        try:
            return json.loads(CHAT_FILE.read_text())["chat_id"]
        except Exception:
            pass
    # 자동 탐지: 사용자가 봇에게 보낸 최근 메시지에서 chat id 추출
    try:
        upd = _api("getUpdates", {"limit": 10})
        for u in reversed(upd.get("result", [])):
            chat = (u.get("message") or u.get("edited_message") or {}).get("chat")
            if chat and chat.get("id"):
                cid = str(chat["id"])
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                CHAT_FILE.write_text(json.dumps(
                    {"chat_id": cid, "name": chat.get("first_name", "")}))
                return cid
    except Exception:
        pass
    return None


def notify(text: str) -> bool:
    """알림 전송. 실패해도 예외를 밖으로 던지지 않는다 (매매 루프 보호)."""
    try:
        if not _token():
            return False
        cid = _chat_id()
        if not cid:
            return False
        _api("sendMessage", {"chat_id": cid, "text": text,
                             "disable_web_page_preview": "true"})
        return True
    except Exception:
        return False
