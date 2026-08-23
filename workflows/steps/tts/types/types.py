from dataclasses import dataclass
from typing import Literal


Encoding = Literal[
    "pcm_s16le",
    "pcm_f32le",
    "mulaw",
    "alaw",
    "opus",
]


Container = Literal[
    "raw",
    "wav",
    "ogg",
    "webm",
]


@dataclass(frozen=True)
class AudioFormat:
    encoding: Encoding
    sample_rate: int
    channels: int
    container: Container = "raw"


@dataclass
class AudioChunk:
    data: bytes
    format: AudioFormat
    timestamp_ns: int
    sequence: int
    is_final: bool = False