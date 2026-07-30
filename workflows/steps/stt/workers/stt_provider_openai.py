'''
A tiny wrapper around the call to the STT API
'''

import httpx
from typing import AsyncGenerator
from yaafpy.types import ExecContext
from workflows.signals import EndOfStream
from workflows.utils import call_stt_from_frames_openai

async def call_stt_openai(http_client: httpx.AsyncClient, frames: list[AudioFrame]) -> str:
    return await call_stt_from_frames_openai(http_client, frames)