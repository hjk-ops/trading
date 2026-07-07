"""사진 답안지 자동채점 (Claude Vision API).

환경변수: ANTHROPIC_API_KEY (설정 시 활성화), ANTHROPIC_MODEL(선택)
클라이언트가 축소한 JPEG(base64)를 받아 틀린 문항 번호를 추출한다.
확신이 낮은 문항은 uncertain으로 분리해 사람이 확인하게 한다.
"""
import json
import os
import re
import urllib.request

API = "https://api.anthropic.com/v1/messages"


def vision_ready():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def grade_photo(image_b64: str, media_type: str, q_numbers: list) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"error": "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
                         "Railway Variables에 키를 추가하면 사진 채점이 활성화됩니다."}
    prompt = (
        f"이 이미지는 채점된 시험 답안지/시험지입니다. 문항 번호는 {q_numbers[0]}~{q_numbers[-1]}번입니다. "
        "채점 표시(빗금, X, 빨간 표시, 감점 등)를 보고 틀린 문항 번호를 찾아주세요. "
        "판독이 애매한 문항은 uncertain에 넣으세요. "
        '반드시 JSON만 출력: {"wrong":[번호...], "uncertain":[번호...]}'
    )
    body = json.dumps({
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": 500,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": media_type, "data": image_b64}},
            {"type": "text", "text": prompt},
        ]}],
    }).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        return {"error": f"API 오류 {e.code}: {detail}"}
    except Exception as e:
        return {"error": f"요청 실패: {e}"}
    text = "".join(b.get("text", "") for b in resp.get("content", []))
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"error": "응답 파싱 실패", "raw": text[:200]}
    try:
        parsed = json.loads(m.group(0))
        valid = set(q_numbers)
        return {"wrong": sorted(set(int(x) for x in parsed.get("wrong", [])) & valid),
                "uncertain": sorted(set(int(x) for x in parsed.get("uncertain", [])) & valid)}
    except Exception:
        return {"error": "JSON 해석 실패", "raw": text[:200]}
