from workflows.steps.stt.config import DEBUG, SAVE_TO_S3
from workflows.steps.stt.workers.debug_stt import debug_stt
from workflows.steps.stt.workers.save_utterance_s3 import save_s3
from workflows.steps.stt.workers.stt_openai import call_stt_openai
from yaafpy.types import ExecContext
from typing import AsyncGenerator
from workflows.signals import EndOfStream, AskUserStillThere, StartSpeaking, WarmUp 
import asyncio

# ════════════════════════════════════════════════════════════════════════════════
# TRANSFORM 2  –  STT
# Reads audio frames from the source, utterance by utterance 
# and converts them to text using STT provider
# list[AudioFrame]  →  str
# ════════════════════════════════════════════════════════════════════════════════

async def stt(
    source: AsyncGenerator,
    ctx:    ExecContext,
) -> AsyncGenerator:
    """
    Receives utterances, handles interruptions via task cancellation,
    and logs raw PCM to disk for debugging.
    """

    current_task = None
    http_client: httpx.AsyncClient = ctx.shared_data["resources"]["http_client"]

    async for item in source:

        if isinstance(item, EndOfStream):
            if current_task and not current_task.done():
                current_task.cancel()
            yield item
            break

        # If we get a AskUserStillThere signal and task is done, yield it
        if isinstance(item, AskUserStillThere) and current_task and current_task.done():
            yield item
   
        # If we get a Stop signal, kill the Whisper task immediately
        if isinstance(item, StartSpeaking):
            if current_task and not current_task.done():
                current_task.cancel()
            yield item

        if isinstance(item, WarmUp):
            # We know audio is coming, but we ignore until UserFinished
            yield item

        if isinstance(item, list): # This is the actual AudioBuffer
            
            if DEBUG:
                asyncio.create_task(debug_stt(item))
            
            if SAVE_TO_S3:
                asyncio.create_task(save_s3(item))

            # Launch Whisper as a task so we can cancel it if a StopAndClear arrives later
            current_task = asyncio.create_task(call_stt_openai(http_client, item))

            try:
                transcript = await current_task
                if transcript: yield transcript
            except asyncio.CancelledError:
                logger.info("STT: Task killed by StartSpeaking signal.")
            finally:
                # Cleanup task if it was orphaned by an error or cancellation
                if not current_task.done():
                    current_task.cancel()