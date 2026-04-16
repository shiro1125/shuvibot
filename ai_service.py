# ai_service.py
# MODIFIED: Gemini 호출 전담 분리 + 검색 판단/쿼리 생성 보조
import asyncio

from google import genai

from config import GEMINI_API_KEY, MODEL_LIST

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")

_client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options={"api_version": "v1beta"},
)


def get_model_list():
    return list(MODEL_LIST)


def is_quota_error(error_text: str) -> bool:
    upper = error_text.upper()
    return any(x in upper for x in ["429", "EXHAUSTED", "QUOTA", "LIMIT", "RATE_LIMIT", "PERMISSION_DENIED"])


def generate_simple_text(prompt: str, model_name: str | None = None) -> str:
    model = model_name or (MODEL_LIST[0] if MODEL_LIST else "models/gemini-2.5-flash-lite")
    response = _client.models.generate_content(
        model=model,
        contents=prompt,
    )
    return (getattr(response, "text", None) or "").strip()


async def generate_reply(model_name: str, system_instruction: str, full_content: str):
    loop = asyncio.get_running_loop()

    if "gemma" in model_name.lower():
        prompt = f"[시스템 지침]\n{system_instruction}\n\n유저 메시지: {full_content}"
        return await loop.run_in_executor(
            None,
            lambda: _client.models.generate_content(
                model=model_name,
                contents=prompt,
            ),
        )

    return await loop.run_in_executor(
        None,
        lambda: _client.models.generate_content(
            model=model_name,
            contents=full_content,
            config={"system_instruction": system_instruction},
        ),
    )
