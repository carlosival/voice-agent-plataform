'''
This step is used to format the audio frame to be sent to the output Transport(WebRTC, WebSocket, etc)
'''

# ════════════════════════════════════════════════════════════════════════════════
# TRANSFORM 5  –  Frame sender  (sink)
# bytes  →  (side-effect: sends AudioFrames to output_track)
# ════════════════════════════════════════════════════════════════════════════════

async def frame_sender(
    source: AsyncGenerator,
    ctx:    ExecContext,
) -> AsyncGenerator:
    """
    Final Sink: Bridge between Step 4 (TTS) and WebRTC Output Track.
    Maintains a 160ms pre-roll buffer to eliminate inter-sentence jitter.
    """
    output_track: AudioOutputTrack = ctx.shared_data["resources"]["output_track"]
    speaking_event: Event          = ctx.shared_data["events"]["speaking_event"]
    SAMPLES      = 960          # 20ms at 48kHz

    async for pcm_bytes in source:
        if speaking_event.is_set():
            continue
        pcm_data = np.frombuffer(pcm_bytes, dtype=np.int16)
        for i in range(0, len(pcm_data), SAMPLES):
            chunk = pcm_data[i:i + SAMPLES]
            if len(chunk) < SAMPLES:
                chunk = np.pad(chunk, (0, SAMPLES - len(chunk)))
            await wait_for(output_track._queue.put(chunk), timeout=2.0)
        
    if False: yield  # ← makes Python treat this as an async generator function  