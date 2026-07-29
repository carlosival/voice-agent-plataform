"""
FastAPI server that accepts Telnyx Media Streaming WebSocket connections and
drives them through the existing `audio_pipeline` (workflows.VOICE_WORKFLOW).

Endpoints:
  POST /texml            -> returns TeXML pointing Telnyx at /ws  (dial-in)
  POST /dialout-webhook   -> returns TeXML pointing Telnyx at /ws  (dial-out, answered call)
  POST /start             -> triggers an outbound call via Telnyx Call Control API
  WS   /ws                -> the actual media stream Telnyx connects to
"""

import asyncio
import logging
import os
import time
import uuid

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, Response
from pydantic import BaseModel

from telnyx_ws_track import TelnyxInputTrack, TelnyxOutputTrack
from audio_pipeline import audio_pipeline  # your existing module from the pasted code

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY")
TELNYX_CONNECTION_ID = os.getenv("TELNYX_CONNECTION_ID")
TELNYX_PHONE_NUMBER = os.getenv("TELNYX_PHONE_NUMBER")
PUBLIC_WS_URL = os.getenv("PUBLIC_WS_URL")  # e.g. wss://your-server.com/ws


# ---------------------------------------------------------------------------
# TeXML: tells Telnyx where to open the WebSocket
# ---------------------------------------------------------------------------

TEXML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}" bidirectionalMode="rtp"></Stream>
  </Connect>
  <Pause length="40"/>
</Response>"""


@app.post("/texml")
async def texml_dialin():
    """Assign this endpoint's URL as your Telnyx number's TeXML application (dial-in)."""
    return Response(content=TEXML_TEMPLATE.format(ws_url=PUBLIC_WS_URL), media_type="application/xml")


@app.post("/dialout-webhook")
async def texml_dialout():
    """Set this as the webhook_url when creating an outbound call (dial-out)."""
    return Response(content=TEXML_TEMPLATE.format(ws_url=PUBLIC_WS_URL), media_type="application/xml")


# ---------------------------------------------------------------------------
# Dial-out trigger
# ---------------------------------------------------------------------------

class DialOutRequest(BaseModel):
    phone_number: str


@app.post("/start")
async def start_call(req: DialOutRequest):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.telnyx.com/v2/calls",
            headers={"Authorization": f"Bearer {TELNYX_API_KEY}"},
            json={
                "connection_id": TELNYX_CONNECTION_ID,
                "to": req.phone_number,
                "from": TELNYX_PHONE_NUMBER,
                "webhook_url": f"{PUBLIC_WS_URL.replace('wss://', 'https://').replace('/ws', '')}/dialout-webhook",
            },
        )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# The actual media stream WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    input_track = TelnyxInputTrack(websocket)

    # Wait for Telnyx's "start" event so we know the stream_id before building
    # the output track. Timeout guards against a connection that never sends it.
    for _ in range(500):  # ~5s at 10ms polling
        if input_track.stream_id is not None:
            break
        await asyncio.sleep(0.01)

    if input_track.stream_id is None:
        logger.error("Never received Telnyx 'start' event; closing connection.")
        await websocket.close()
        return

    output_track = TelnyxOutputTrack(websocket, input_track.stream_id)

    ctx = build_exec_context(websocket, input_track, output_track)

    try:
        await audio_pipeline(input_track, ctx)
    finally:
        input_track.stop()
        output_track.stop()


# ---------------------------------------------------------------------------
# ExecContext construction
#
# NOTE: fill this in to match however ExecContext / tracer / tools are built
# elsewhere in your app today (you likely already have this for the WebRTC
# path — reuse that factory and just swap the "resources" block below).
# ---------------------------------------------------------------------------

def build_exec_context(websocket, input_track, output_track):
    from yaafpy import ExecContext  # adjust import to match your project layout

    trace_id = str(uuid.uuid4())

    ctx = ExecContext(
        session_id=input_track.stream_id,
        metadata={},
        message_history=[],
        events=[],
        resources={
            "output_track": output_track,
            "pc": None,  # no RTCPeerConnection on this transport
            "tracer": get_tracer(),  # your existing tracer factory
        },
        # config=...  # MAX_TOKENS, PERMISSIONS, etc. — reuse your existing defaults
    )

    ctx.shared_data["trace_context"] = {"trace_id": trace_id}
    ctx.shared_data["peer_state"] = {"connected_at": time.time()}
    ctx.shared_data["tools"] = {}  # populate with your registered tools as usual

    return ctx


def get_tracer():
    """Return whatever tracer/langfuse client instance your app normally uses."""
    from your_tracing_module import tracer  # adjust to your actual module
    return tracer


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)