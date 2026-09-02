import asyncio
from typing import AsyncGenerator
from yaafpy.types import ExecContext
from yaafpy import StreamWorkflow

from workflows.utils import (
    layered_has_speech,
    call_stt_from_frames_openai,
    call_stt_from_frames_speaches,
    call_llm_stream_openai,
    call_tts_stream,
    pcm_to_wav,
    frames_to_pcm,
    silero_has_speech_from_numpy,
    frames_to_mono_int16
)

# ════════════════════════════════════════════════════════════════════════════════
# TRANSFORM 4  –  TTS
# str  →  bytes  (WAV blob per sentence)
# ════════════════════════════════════════════════════════════════════════════════

async def tts_stream(
    source: AsyncGenerator,
    ctx:    ExecContext,
) -> AsyncGenerator[bytes, None]:
    """
    Calls Speaches Kokoro-82M per sentence chunk via call_tts_stream.
    Forwards raw PCM byte chunks as they arrive for minimal latency.
    Skips synthesis entirely if speaking_event was set between LLM chunks.
    """

    tasks= []
    http_client:    httpx.AsyncClient   = ctx.shared_data["resources"]["http_client"]
    output_track: AudioOutputTrack = ctx.shared_data["resources"]["output_track"]
    current_task = None
    tts_queue = asyncio.Queue()
    
    # 3. DEFINE THE SYNTHESIS WORKER
    async def tts_worker(client: httpx.AsyncClient, track: AudioOutputTrack):
        while True:
            try:
                text = await tts_queue.get()
                if text is None:
                    break
                
                gen = call_tts_stream(http_client=http_client, text=text, debug=True)
                frame_count = 0
                
                async for pcm_chunk in gen:
                    # The code will only block here if 'call_tts_stream' hangs.
                    # As long as chunks are coming, this keeps running.
                    await track.push_pcm_bytes(pcm_chunk)
                    frame_count += 1
                
                if frame_count > 0:
                    await track.add_silence(duration_frames=20)
                    logger.info(f"TTS Worker: Finished {frame_count} frames for: {text}")
                
            except CancelledError:
                # Still vital for barge-in!
                logger.debug("TTS Worker: Cancelled (Barge-in).")
                raise 
            except Exception as e:
                logger.error(f"TTS Worker Error: {e}")

    
    # 1. Warm up the track for first time
    #await output_track.add_silence(duration_frames=15)

    current_task = create_task(tts_worker(http_client, output_track))

    try:
        async for sentence in source:
            if isinstance(sentence, WarmUp):
                logger.info(f"TTS received WarmUp signal.")
                await output_track.add_silence(duration_frames=50)
                await tts_queue.put("¡Hola! ¿Cómo puedo ayudarte?")

            if isinstance(sentence, EndOfStream):
                logger.info("TTS: EndOfStream received. Cleaning up.")
                # Optional: Send a goodbye message before killing
                await wait_for(tts_queue.put("¡Hasta luego!"), timeout=2.0) 
                await wait_for(tts_queue.put(None), timeout=2.0)
                break
            # 1. SIGNAL HANDLING (The "Kill Switch")
            if isinstance(sentence, StartSpeaking):
                logger.info("[AUDIO_KILL] TTS received StartSpeaking. Purging output track.")
                # Clear pending sentences
                while not tts_queue.empty():
                    tts_queue.get_nowait()
                # Cancel whatever is currently synthesizing
                if current_task and not current_task.done():
                    current_task.cancel()
                    try:
                        await current_task
                    except CancelledError:
                        pass
                output_track.purge()
                # Restart the sequential worker
                current_task = create_task(tts_worker(http_client, output_track))
                continue

            # 2. DATA HANDLING (The Sentence)
            if isinstance(sentence, str):
                logger.info(f"TTS received sentence: '{sentence}'")
                await wait_for(tts_queue.put(sentence), timeout=2.0)
            
            # 3. ASK USER STILL THERE
            if isinstance(sentence, AskUserStillThere):
                logger.info("TTS received AskUserStillThere signal.")
                if tts_queue.empty():
                    await wait_for(tts_queue.put("¿Te puedo ayudar en algo más?"), timeout=2.0)
            
    except Exception as e:
        logger.error(f"TTS Main Loop Exception: {e}")
        raise
    finally:
        await wait_for(tts_queue.put(None), timeout=2.0)  # shutdown sentinel
        if current_task and not current_task.done():
            current_task.cancel()
        # This is critical for yaafpy
        raise WorkflowAbortException("End of stream.")

    if False: yield  # ← makes Python treat this as an async generator function 

