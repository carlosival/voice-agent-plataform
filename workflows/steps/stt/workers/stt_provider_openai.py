'''
A tiny wrapper around the call to the STT API
'''

import httpx
from typing import AsyncGenerator, Optional
from yaafpy.types import ExecContext
from workflows.signals import EndOfStream
from ..utils import call_stt_openai
from av import AudioFrame
import os

STT_BASE_URL = os.getenv("STT_BASE_URL",  "http://speaches:8000")
STT_MODEL    = os.getenv("STT_MODEL",     "Systran/faster-whisper-large-v3")
STT_LANGUAGE = os.getenv("STT_LANGUAGE",  "es")
STT_API_KEY  = os.getenv("STT_API_KEY")


async def call_stt(frames: list[AudioFrame], model: str = STT_MODEL, language: str = STT_LANGUAGE, api_key: str = STT_API_KEY, base_url: str = STT_BASE_URL, http_client: Optional[httpx.AsyncClient] = None) -> str:
    return await call_stt_openai(frames, model, language, api_key, base_url, http_client)