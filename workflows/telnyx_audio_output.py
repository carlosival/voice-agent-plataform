# ──────────────────────────────────────────────
# TelnyxAudioOutput — outbound counterpart to AudioOutputTrack
# Pushes TTS/PCM audio back over the Telnyx bidirectional WS stream.
# Requires stream_bidirectional_mode="rtp" on the Telnyx side.
# ──────────────────────────────────────────────
import asyncio
import base64
import json
import logging
from typing import Optional

import av
import numpy as np
from av import AudioFrame
from av.audio.resampler import AudioResampler

logger = logging.getLogger(__name__)

SOURCE_SAMPLE_RATE = 48000     # rate your TTS/pipeline outputs
SAMPLES_PER_10MS    = 480      # at 48kHz
CHUNK_MS             = 20      # RTP frames sent to Telnyx, min recommended

# Telnyx bidirectionalCodec -> PyAV raw-PCM encoder + bytes/sample
_ENCODER_MAP = {
    "PCMU": ("pcm_mulaw", 1),
    "PCMA": ("pcm_alaw", 1),
    "L16":  (None, 2),   # linear PCM16, no codec needed
}
# NOTE: G722/OPUS/AMR-WB are frame-based codecs (not simple raw-sample
# codecs like the above) and need different framing — not covered here.


class TelnyxAudioOutput:
    """
    Outbound counterpart to AudioOutputTrack — pushes audio back over the
    SAME websocket the inbound Telnyx stream is on, instead of a WebRTC
    track. Resamples from SOURCE_SAMPLE_RATE down to the call's negotiated
    rate/codec and sends `media` frames per Telnyx's RTP bidirectional mode.
    """

    def __init__(self, websocket, encoding: str = "PCMU", target_sample_rate: int = 8000):
        if encoding not in _ENCODER_MAP:
            raise ValueError(f"Unsupported bidirectional encoding: {encoding}")

        self._ws          = websocket
        self._encoding     = encoding
        self._target_rate  = target_sample_rate
        self._queue: asyncio.Queue[Optional[np.ndarray]] = asyncio.Queue(maxsize=200)
        self._ended        = False

        codec_name, bytes_per_sample = _ENCODER_MAP[encoding]
        self._bytes_per_chunk = int(target_sample_rate / 1000 * CHUNK_MS * bytes_per_sample)

        self._resampler = AudioResampler(format="s16", layout="mono", rate=target_sample_rate)
        self._encoder = av.CodecContext.create(codec_name, "w") if codec_name else None
        if self._encoder is not None:
            self._encoder.sample_rate = target_sample_rate
            self._encoder.layout = "mono"
            self._encoder.format = "s16"

        self._send_buffer = bytearray()
        self._sender_task = asyncio.create_task(self._run())

    async def _run(self):
        try:
            while True:
                pcm = await self._queue.get()
                if pcm is None:  # sentinel: stop
                    break
                await self._encode_and_buffer(pcm)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("TelnyxAudioOutput: sender loop crashed")

    async def _encode_and_buffer(self, pcm: np.ndarray):
        frame = AudioFrame.from_ndarray(pcm[None, :], layout="mono")
        frame.sample_rate = SOURCE_SAMPLE_RATE

        resampled = self._resampler.resample(frame)
        if resampled is None:
            return
        if not isinstance(resampled, list):
            resampled = [resampled]

        for rframe in resampled:
            if self._encoder is not None:
                for packet in self._encoder.encode(rframe):
                    self._send_buffer.extend(bytes(packet))
            else:
                # L16 is big-endian per RTP convention (RFC 3551)
                samples = rframe.to_ndarray().flatten().astype("<i2")
                self._send_buffer.extend(samples.astype(">i2").tobytes())

        while len(self._send_buffer) >= self._bytes_per_chunk:
            chunk = bytes(self._send_buffer[: self._bytes_per_chunk])
            del self._send_buffer[: self._bytes_per_chunk]
            await self._send_media(chunk)

    async def _send_media(self, payload: bytes):
        msg = {"event": "media", "media": {"payload": base64.b64encode(payload).decode("ascii")}}
        await self._ws.send(json.dumps(msg))

    async def flush(self):
        """Send any partial chunk left in the buffer (e.g. end of an utterance)."""
        if self._send_buffer:
            await self._send_media(bytes(self._send_buffer))
            self._send_buffer.clear()

    async def push_audio(self, pcm: np.ndarray):
        """Push a numpy int16 array at 48kHz — chunks into 10ms frames."""
        pcm = pcm.astype(np.int16)
        for i in range(0, len(pcm), SAMPLES_PER_10MS):
            chunk = pcm[i : i + SAMPLES_PER_10MS]
            if len(chunk) < SAMPLES_PER_10MS:
                chunk = np.pad(chunk, (0, SAMPLES_PER_10MS - len(chunk)))
            await self._queue.put(chunk.copy())

    async def push_wav(self, wav_bytes: bytes):
        """Push raw WAV bytes — resamples to 48kHz if needed, then chunks."""
        import wave, io
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            raw      = wf.readframes(wf.getnframes())
            src_rate = wf.getframerate()
            src_ch   = wf.getnchannels()
            pcm      = np.frombuffer(raw, dtype=np.int16)

        if src_rate != SOURCE_SAMPLE_RATE or src_ch != 1:
            up = AudioResampler(format="s16", layout="mono", rate=SOURCE_SAMPLE_RATE)
            frame = AudioFrame.from_ndarray(
                pcm[None, :] if src_ch == 1 else pcm.reshape(src_ch, -1),
                layout="mono" if src_ch == 1 else "stereo",
            )
            frame.sample_rate = src_rate
            out = up.resample(frame)
            out = out if isinstance(out, list) else [out]
            pcm = np.concatenate([f.to_ndarray().flatten() for f in out]).astype(np.int16)

        await self.push_audio(pcm)
        await self.flush()

    async def push_pcm_bytes(self, raw_bytes: bytes):
        """Push raw PCM16 @ 48kHz bytes."""
        await self.push_audio(np.frombuffer(raw_bytes, dtype=np.int16))
        await self.flush()

    async def clear(self):
        """
        Barge-in: drop everything queued/buffered locally AND tell Telnyx
        to stop playback and flush what it already has.
        """
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._send_buffer.clear()
        try:
            await self._ws.send(json.dumps({"event": "clear"}))
        except Exception:
            logger.exception("TelnyxAudioOutput: failed to send clear frame")

    def stop(self):
        self._ended = True
        self._queue.put_nowait(None)
        self._sender_task.cancel()