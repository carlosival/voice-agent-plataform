
import numpy as np
from enum import Enum
from dataclasses import dataclass

# --- Assumed shape of your Encoding enum; align with your real definition ---
class Encoding(str, Enum):
    PCM_S16LE = "pcm_s16le"
    PCM_S32LE = "pcm_s32le"
    PCM_F32LE = "pcm_f32le"
    PCM_U8 = "pcm_u8"
    MULAW = "mulaw"
    ALAW = "alaw"
    OPUS = "opus"

class Container(str, Enum):
    RAW = "raw"
    WAV = "wav"
    OGG = "ogg"
    MP3 = "mp3"
    AAC = "aac"
    OPUS = "opus"
    FLAC = "flac"
    ALAW = "alaw"
    ULAW = "ulaw"

_DTYPE_MAP = {
    Encoding.PCM_S16LE: np.int16,
    Encoding.PCM_S32LE: np.int32,
    Encoding.PCM_F32LE: np.float32,
    Encoding.PCM_U8: np.uint8,
}


@dataclass(frozen=True)
class AudioFormat:
    encoding: Encoding
    sample_rate: int
    channels: int
    sample_width: int
    container: Container = "raw"
    


@dataclass
class AudioChunk:
    data: bytes
    format: AudioFormat
    timestamp_ns: int
    sequence: int
    is_final: bool = False

WEBRTC_AUDIO_FORMAT = AudioFormat(
    encoding=Encoding.PCM_S16LE,
    sample_rate=48000,
    channels=1,
    container="raw",
    sample_width=2,
)

OPENAI_TTS_FORMAT = AudioFormat(
    encoding=Encoding.PCM_S16LE,
    sample_rate=24000,
    channels=1,
    container="raw",
    sample_width=2,
)

GROQ_TTS_FORMAT = AudioFormat(
    encoding=Encoding.PCM_S16LE,
    sample_rate=24000,
    channels=1,
    container="raw",
    sample_width=2,
)


TELNYX_AUDIO_FORMAT = AudioFormat(
    encoding=Encoding.PCM_S16LE,
    sample_rate=8000,
    channels=1,
    container="raw",
    sample_width=2,
)


def get_stt_provider_format(provider_name: str) -> AudioFormat:
    if provider_name == "openai":
        return OPENAI_STT_FORMAT
    elif provider_name == "groq":
        return GROQ_STT_FORMAT
    elif provider_name == "telnyx":
        return SPEACHES_STT_FORMAT
    else:
        raise ValueError(f"Unknown provider: {provider_name}")

def get_output_format(output) -> AudioFormat:
    """
    Returns the expected audio format for the given output.
    """
    if isinstance(output, AudioOutputTrack):
        return WEBRTC_AUDIO_FORMAT
    # Add other output types here
        