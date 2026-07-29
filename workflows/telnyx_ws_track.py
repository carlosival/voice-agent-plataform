"""
Adapters that let a Telnyx Media Streaming WebSocket connection stand in for
the aiortc `input_track` / `output_track` your pipeline currently gets from a
WebRTC PeerConnection.

Telnyx WS protocol (same shape as Twilio's):
  Inbound JSON events -> {"event": "connected" | "start" | "media" | "stop", ...}
  media.payload        -> base64, header-less RTP audio, default PCMU (u-law) 8kHz mono
  To send audio back    -> send a JSON {"event": "media", "media": {"payload": <b64>}}

NOTE: `audioop` was removed from the stdlib in Python 3.13. If you're on 3.13+,
`pip install audioop-lts` gives you the same module back as a drop-in.
"""

import asyncio
import base64
import fractions
import json
import logging

import audioop  # stdlib <=3.12, or `audioop-lts` package on 3.13+
import numpy as np
from av import AudioFrame
from aiortc.mediastreams import MediaStreamTrack, MediaStreamError

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000  # Telnyx default codec (PCMU/PCMA) is 8kHz


class TelnyxInputTrack(MediaStreamTrack):
    """Wraps a Telnyx WebSocket as an aiortc-compatible audio MediaStreamTrack.

    Feed this directly into `track_frames(input_track)` exactly like you would
    an aiortc remote track — `.recv()` yields `av.AudioFrame`s.
    """

    kind = "audio"

    def __init__(self, websocket):
        super().__init__()
        self._ws = websocket
        self._queue: asyncio.Queue = asyncio.Queue()
        self._timestamp = 0
        self.stream_id: str | None = None
        self.call_control_id: str | None = None
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        try:
            async for raw in self._ws.iter_text():
                msg = json.loads(raw)
                event = msg.get("event")

                if event == "start":
                    start = msg.get("start", {})
                    self.stream_id = start.get("stream_id") or msg.get("stream_id")
                    self.call_control_id = start.get("call_control_id")
                    logger.info(f"Telnyx stream started: {self.stream_id}")

                elif event == "media":
                    payload_b64 = msg["media"]["payload"]
                    ulaw_bytes = base64.b64decode(payload_b64)
                    pcm_bytes = audioop.ulaw2lin(ulaw_bytes, 2)  # -> 16-bit PCM
                    await self._queue.put(pcm_bytes)

                elif event == "stop":
                    logger.info("Telnyx stream stopped")
                    break

        except Exception as e:
            logger.error(f"TelnyxInputTrack read loop error: {e}", exc_info=True)
        finally:
            await self._queue.put(None)  # signal EOF to recv()

    async def recv(self) -> AudioFrame:
        pcm_bytes = await self._queue.get()
        if pcm_bytes is None:
            raise MediaStreamError("Telnyx stream ended")

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).reshape(1, -1)
        frame = AudioFrame.from_ndarray(samples, format="s16", layout="mono")
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, SAMPLE_RATE)
        self._timestamp += samples.shape[1]
        return frame

    def stop(self):
        if not self._reader_task.done():
            self._reader_task.cancel()
        super().stop()


class TelnyxOutputTrack:
    """Buffers outbound audio and streams it to Telnyx as `media` WS events.

    Exposes `.purge()` / `.stop()` to match what your pipeline's cleanup code
    already calls on `ctx.shared_data["resources"]["output_track"]`. Add a
    `.write(pcm_bytes)` call wherever your workflow currently writes frames to
    the aiortc output track — swap that call site for this instead.
    """

    def __init__(self, websocket, stream_id: str):
        self._ws = websocket
        self.stream_id = stream_id
        self._queue: asyncio.Queue = asyncio.Queue()
        self._sender_task = asyncio.create_task(self._send_loop())

    async def write(self, pcm_bytes: bytes):
        """PCM16 mono @ 8kHz in -> queued for sending as u-law to Telnyx."""
        await self._queue.put(pcm_bytes)

    async def _send_loop(self):
        try:
            while True:
                pcm_bytes = await self._queue.get()
                if pcm_bytes is None:
                    break
                ulaw_bytes = audioop.lin2ulaw(pcm_bytes, 2)
                payload_b64 = base64.b64encode(ulaw_bytes).decode("ascii")
                msg = {
                    "event": "media",
                    "stream_id": self.stream_id,
                    "media": {"payload": payload_b64},
                }
                await self._ws.send_text(json.dumps(msg))
        except Exception as e:
            logger.error(f"TelnyxOutputTrack send loop error: {e}", exc_info=True)

    def purge(self):
        """Drop any buffered-but-unsent audio (e.g. on barge-in)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        # Optionally also tell Telnyx to clear its own playback buffer:
        asyncio.create_task(
            self._ws.send_text(json.dumps({"event": "clear", "stream_id": self.stream_id}))
        )

    def stop(self):
        self._queue.put_nowait(None)
        if not self._sender_task.done():
            self._sender_task.cancel()