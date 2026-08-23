import numpy as np
from workflows.steps.outputs.types import AudioFormat
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator


try:
    from scipy.signal import resample_poly
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


# --- Assumed shape of your Encoding enum; align with your real definition ---
class Encoding(str, Enum):
    PCM_S16LE = "pcm_s16le"
    PCM_S32LE = "pcm_s32le"
    PCM_F32LE = "pcm_f32le"
    PCM_U8 = "pcm_u8"


_DTYPE_MAP = {
    Encoding.PCM_S16LE: np.int16,
    Encoding.PCM_S32LE: np.int32,
    Encoding.PCM_F32LE: np.float32,
    Encoding.PCM_U8: np.uint8,
}


class AudioConverter:
    """
    Converts raw PCM numpy arrays between sample rate, channel count,
    and bit-depth/encoding. Internally normalizes to float32 [-1, 1]
    to make resampling and channel mixing safe, then casts to the
    target dtype at the end.
    """
    def __init__(self, input_format: AudioFormat, output_format: AudioFormat):
        self.input_format = input_format
        self.output_format = output_format



    def convert(self, audio_data: np.ndarray) -> np.ndarray:
        if self.input_format.encoding == self.output_format.encoding and \
            self.input_format.sample_rate == self.output_format.sample_rate and \
            self.input_format.channels == self.output_format.channels and \
            self.input_format.container == self.output_format.container and \
            self.input_format.sample_width == self.output_format.sample_width:
            return audio_data

        # 1. Reshape flat interleaved data -> (frames, channels)
        data = self._to_frames(audio_data, self.input_format.channels)

        # 2. Normalize to float32 [-1, 1] regardless of source encoding
        data = self._to_float32(data, self.input_format.encoding)

        # 3. Resample (per-channel) if sample rates differ
        if self.input_format.sample_rate != self.output_format.sample_rate:
            data = self._resample(
                data,
                self.input_format.sample_rate,
                self.output_format.sample_rate,
            )

        # 4. Up/down-mix channels if needed
        if self.input_format.channels != self.output_format.channels:
            data = self._convert_channels(data, self.output_format.channels)

        # 5. Cast float32 -> target encoding
        data = self._from_float32(data, self.output_format.encoding)

        # 6. Flatten back to interleaved 1-D array (what you feed to bytes)
        return data.reshape(-1)