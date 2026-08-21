'''
A tiny wrapper around the call to the STT API
'''

import httpx
from typing import AsyncGenerator, Optional
from yaafpy.types import ExecContext
from workflows.signals import EndOfStream
from workflows.stt.utils.speech_to_text import call_stt_from_frames_openai
from av import AudioFrame

async def call_stt(frames: list[AudioFrame], model: str = STT_MODEL, language: str = STT_LANGUAGE, api_key: str = STT_API_KEY, base_url: str = STT_BASE_URL, http_client: Optional[httpx.AsyncClient] = None) -> str:
    return await call_stt_from_frames_openai(frames, model, language, api_key, base_url, http_client)