# 📋 main.py · [과제 백엔드] 분리수거 도우미 API — 사진을 받아 정해 둔 칸(JSON)으로 정리 (Vercel 에 올릴 main.py · POST 한 번에 요청 1번)
# · ★ (직접 작성) 표시가 붙은 곳만 내 주제로 바꿈 — 화면(app.py)은 GET / 에서 이름 · 칸을 가져감
# · 키는 환경 변수 GEMINI_API_KEY · 접근 코드는 APP_ACCESS_CODE (코드 · 저장소에 적지 않음)
import base64
import binascii
import json
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

MODEL_NAME = "gemini-3.5-flash-lite"

# ★ (직접 작성) ① 서비스 이름 · 아이콘 · 한 줄 소개 — 화면이 GET / 로 받아 제목으로 씀
APP_TITLE = "분리수거 도우미"
APP_ICON = "♻️"
APP_DESCRIPTION = "버릴 물건 사진을 찍으면 재질을 알아보고, 어떻게 분리배출하는지 알려 줍니다"

# ★ (직접 작성) ② 사진을 보고 할 일 — 역할 · 할 일 · 모를 때
PROMPT = """너는 자취하는 대학생의 분리수거를 도와주는 도우미야.
사진 속 버릴 물건이 무엇인지, 어떤 재질인지 알아보고 한국의 분리배출 기준에 맞춰 버리는 방법을 알려 줘.
버리는 방법은 '1. … 2. … 3. …' 처럼 번호를 붙여 3단계 이내로 짧게 적어.
사진에서 알아볼 수 없는 칸은 '확인 불가' 라고 적어.
사진에 버릴 물건이 없으면 모든 칸에 '버릴 물건이 아님' 이라고 적어."""

# ★ (직접 작성) ③ 결과로 받을 칸 이름 : 설명 (3~5개)
FIELDS = {
    "물건": "사진 속 버릴 물건 이름",
    "재질": "물건의 재질 (예: 플라스틱(PET), 종이, 캔, 유리, 일반쓰레기)",
    "버리는 방법": "번호를 붙인 3단계 이내의 분리배출 방법",
    "주의할 점": "헷갈리기 쉬운 점이나 주의할 점 한 문장",
}

SCHEMA = {"type": "object", "properties": {name: {"type": "string", "description": text} for name, text in FIELDS.items()},
          "required": list(FIELDS)}
app = FastAPI(title=APP_TITLE, description=APP_DESCRIPTION)


class PhotoRequest(BaseModel):
    image_b64: str = Field(min_length=1, max_length=4_000_000, description="사진(JPEG)을 base64 로 바꾼 글자")


class Result(BaseModel):
    result: dict[str, str]
    tokens: int | None = None


def check_access(access_code):
    expected = os.environ.get("APP_ACCESS_CODE")
    if expected and access_code != expected:
        raise HTTPException(status_code=401, detail="접근 코드가 틀렸습니다 — 헤더 X-Access-Code 를 확인하세요")


def get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="서버에 GEMINI_API_KEY 가 없습니다 — 환경 변수를 확인하세요")
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=120_000, retry_options=types.HttpRetryOptions(http_status_codes=[500, 503])),
    )


@app.get("/")
def home():
    """화면이 제목 · 아이콘 · 소개 · 칸 이름을 가져가는 주소 (요청 없음)"""
    return {"name": APP_TITLE, "icon": APP_ICON, "description": APP_DESCRIPTION, "fields": list(FIELDS)}


@app.post("/analyze", response_model=Result)
def analyze(request: PhotoRequest, x_access_code: str | None = Header(default=None)):
    check_access(x_access_code)
    try:
        base64.b64decode(request.image_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="base64 글자가 아닙니다")
    client = get_client()
    try:
        reply = client.interactions.create(
            model=MODEL_NAME, store=False,
            input=[{"type": "text", "text": PROMPT}, {"type": "image", "data": request.image_b64, "mime_type": "image/jpeg"}],
            response_format={"type": "text", "mime_type": "application/json", "schema": SCHEMA},
        )
    except Exception as error:
        code = getattr(error, "status_code", None)
        raise HTTPException(status_code=429 if code == 429 else 502, detail=f"Gemini 요청 실패 (상태 번호 {code})")
    try:
        result = json.loads(reply.output_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="답이 JSON 모양이 아닙니다 — 다시 보내 보세요")
    return Result(result={name: str(result.get(name, "")) for name in FIELDS}, tokens=reply.usage.total_tokens)
