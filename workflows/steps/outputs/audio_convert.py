import asyncio
import logging
import sys

import numpy as np
from .output_expect_format import AudioFormat, Encoding, _DTYPE_MAP
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator


try:
    from scipy.signal import resample_poly
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


class AudioConverter:
    """
    Convierte audio PCM en bytes crudos entre distintos formatos
    (sample_rate, channels, encoding). Mantiene estado interno de
    bytes sobrantes entre llamadas, por lo que UNA instancia debe
    usarse para UN solo stream continuo — no reutilizar entre streams
    distintos sin llamar a reset().
    """

    def __init__(self, input_format: AudioFormat, output_format: AudioFormat):
        self.input_format = input_format
        self.output_format = output_format
        self._leftover = b""

        if input_format.encoding not in _DTYPE_MAP and input_format.encoding != "pcm_s24le":
            raise ValueError(f"Encoding no soportado: {input_format.encoding}")

    def reset(self) -> None:
        """Limpia el buffer de bytes sobrantes. Llamar al iniciar un nuevo stream."""
        self._leftover = b""

    def convert(self, raw: bytes) -> bytes:
        """
        Convierte un chunk de bytes PCM crudos del input_format al output_format.
        Puede devolver b"" si el chunk recibido no alcanza para formar ni una
        muestra completa (los bytes quedan guardados para la próxima llamada).
        """
        if self.input_format == self.output_format:
            return raw

        data = self._leftover + raw
        arr, self._leftover = self._bytes_to_array(data)

        if arr.size == 0:
            return b""

        arr = self._to_frames(arr, self.input_format.channels)
        arr = self._to_float32(arr, self.input_format.encoding)

        if self.input_format.sample_rate != self.output_format.sample_rate:
            arr = self._resample(arr, self.input_format.sample_rate, self.output_format.sample_rate)

        if self.input_format.channels != self.output_format.channels:
            arr = self._convert_channels(arr, self.output_format.channels)

        arr = self._from_float32(arr, self.output_format.encoding)
        return self._array_to_bytes(arr.reshape(-1), self.output_format.encoding)

    def flush(self) -> bytes:
        """
        Llamar al terminar el stream. Si quedan bytes sobrantes que nunca
        llegaron a formar una muestra completa (chunk cortado a mitad de
        muestra justo al final), se descartan y se devuelven vacíos —
        no hay forma de reconstruir una muestra incompleta.
        """
        if self._leftover:
            self._leftover = b""
        return b""

    # ---------- bytes <-> ndarray ----------

    def _item_size(self, encoding: str) -> int:
        if encoding == "pcm_s24le":
            return 3
        return np.dtype(_DTYPE_MAP[encoding]).itemsize

    def _bytes_to_array(self, data: bytes) -> tuple[np.ndarray, bytes]:
        itemsize = self._item_size(self.input_format.encoding)
        usable_len = len(data) - (len(data) % itemsize)
        usable, leftover = data[:usable_len], data[usable_len:]

        if self.input_format.encoding == "pcm_s24le":
            arr = self._pcm24_bytes_to_array(usable)
        else:
            dtype = _DTYPE_MAP[self.input_format.encoding]
            arr = np.frombuffer(usable, dtype=dtype).copy()  # copy: frombuffer es read-only

        return arr, leftover

    def _array_to_bytes(self, arr: np.ndarray, encoding: str) -> bytes:
        if encoding == "pcm_s24le":
            return self._array_to_pcm24_bytes(arr)
        return arr.tobytes()

    @staticmethod
    def _pcm24_bytes_to_array(raw: bytes) -> np.ndarray:
        u8 = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        val = (u8[:, 0].astype(np.int32)
               | (u8[:, 1].astype(np.int32) << 8)
               | (u8[:, 2].astype(np.int32) << 16))
        return np.where(val & 0x800000, val | ~0xFFFFFF, val)

    @staticmethod
    def _array_to_pcm24_bytes(arr: np.ndarray) -> bytes:
        arr = arr.astype(np.int32) & 0xFFFFFF
        out = bytearray(len(arr) * 3)
        out[0::3] = (arr & 0xFF).astype(np.uint8).tobytes()
        out[1::3] = ((arr >> 8) & 0xFF).astype(np.uint8).tobytes()
        out[2::3] = ((arr >> 16) & 0xFF).astype(np.uint8).tobytes()
        return bytes(out)

    # ---------- pipeline de conversión (igual que antes) ----------

    @staticmethod
    def _to_frames(data: np.ndarray, channels: int) -> np.ndarray:
        return data.reshape(-1, channels) if channels > 1 else data.reshape(-1, 1)

    @staticmethod
    def _to_float32(data: np.ndarray, encoding: str) -> np.ndarray:
        if encoding == "pcm_f32le":
            return data.astype(np.float32, copy=False)
        if encoding == "pcm_u8":
            return (data.astype(np.float32) - 128.0) / 128.0
        if encoding == "pcm_s24le":
            return data.astype(np.float32) / (2 ** 23)
        info = np.iinfo(_DTYPE_MAP[encoding])
        return data.astype(np.float32) / max(abs(info.min), info.max)

    @staticmethod
    def _from_float32(data: np.ndarray, encoding: str) -> np.ndarray:
        data = np.clip(data, -1.0, 1.0)
        if encoding == "pcm_f32le":
            return data.astype(np.float32)
        if encoding == "pcm_u8":
            return ((data * 128.0) + 128.0).astype(np.uint8)
        if encoding == "pcm_s24le":
            return (data * (2 ** 23 - 1)).astype(np.int32)
        info = np.iinfo(_DTYPE_MAP[encoding])
        scale = max(abs(info.min), info.max)
        return (data * scale).astype(_DTYPE_MAP[encoding])

    @staticmethod
    def _resample(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        if src_rate == dst_rate:
            return data
        if _HAS_SCIPY:
            gcd = np.gcd(src_rate, dst_rate)
            up, down = dst_rate // gcd, src_rate // gcd
            return resample_poly(data, up, down, axis=0).astype(np.float32)
        n_src = data.shape[0]
        n_dst = int(round(n_src * dst_rate / src_rate))
        src_idx = np.arange(n_src)
        dst_idx = np.linspace(0, n_src - 1, n_dst)
        out = np.empty((n_dst, data.shape[1]), dtype=np.float32)
        for ch in range(data.shape[1]):
            out[:, ch] = np.interp(dst_idx, src_idx, data[:, ch])
        return out

    @staticmethod
    def _convert_channels(data: np.ndarray, target_channels: int) -> np.ndarray:
        current = data.shape[1]
        if current == target_channels:
            return data
        if current == 1 and target_channels > 1:
            return np.repeat(data, target_channels, axis=1)
        if current > 1 and target_channels == 1:
            return data.mean(axis=1, keepdims=True).astype(np.float32)
        if target_channels > current:
            reps = int(np.ceil(target_channels / current))
            return np.tile(data, (1, reps))[:, :target_channels]
        return data[:, :target_channels]



# ─── Test ─────────────────────────────────────────────────────────────────────
# docker exec -it worker-1 python3 -m workflows.steps.outputs.audio_convert

logger = logging.getLogger(__name__)

_results: list[bool] = []


def _check(name: str, condition: bool, detail: str = "") -> bool:
    _results.append(condition)
    if condition:
        logger.info("PASS: %s", name)
    else:
        logger.error("FAIL: %s%s", name, f" — {detail}" if detail else "")
    return condition


def _make_tone(freq_hz: float, duration_s: float, sample_rate: int, channels: int = 1,
               dtype=np.int16, amplitude: float = 0.5) -> bytes:
    """Generate a sine tone as interleaved PCM bytes, for use as test input."""
    n_samples = int(duration_s * sample_rate)
    t = np.arange(n_samples) / sample_rate
    tone = np.sin(2 * np.pi * freq_hz * t) * amplitude

    if channels > 1:
        tone = np.tile(tone[:, None], (1, channels))

    if dtype == np.int16:
        arr = (tone * 32767).astype(np.int16)
    elif dtype == np.int32:
        arr = (tone * 2147483647).astype(np.int32)
    elif dtype == np.float32:
        arr = tone.astype(np.float32)
    elif dtype == np.uint8:
        arr = ((tone * 127) + 128).astype(np.uint8)
    else:
        raise ValueError(dtype)

    return arr.reshape(-1).tobytes()


def _chunk_bytes(data: bytes, chunk_size: int):
    """Split bytes into fixed-size pieces, simulating network chunking."""
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]


async def _test_passthrough() -> None:
    logger.info("--- identity conversion is a passthrough ---")
    fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    conv = AudioConverter(fmt, fmt)
    raw = _make_tone(440, 0.02, 48000, channels=1, dtype=np.int16)
    out = conv.convert(raw)
    _check("passthrough returns identical bytes", out == raw)
    _check("passthrough length matches (1920 bytes for 20ms@48k/16-bit/mono)", len(out) == 1920, f"got {len(out)}")


async def _test_upsample() -> None:
    logger.info("--- resample 24kHz -> 48kHz ---")
    src_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=24000, channels=1, sample_width=2)
    dst_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    conv = AudioConverter(src_fmt, dst_fmt)
    raw = _make_tone(440, 0.5, 24000, channels=1, dtype=np.int16)
    out = conv.convert(raw)
    out_arr = np.frombuffer(out, dtype=np.int16)
    expected_len = 24000
    _check("upsampled sample count ~ 2x input", abs(len(out_arr) - expected_len) <= 2,
           f"got {len(out_arr)}, expected ~{expected_len}")
    _check("output amplitude in valid int16 range", out_arr.max() <= 32767 and out_arr.min() >= -32768)


async def _test_downsample() -> None:
    logger.info("--- resample 48kHz -> 16kHz ---")
    src_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    dst_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=16000, channels=1, sample_width=2)
    conv = AudioConverter(src_fmt, dst_fmt)
    raw = _make_tone(440, 0.3, 48000, channels=1, dtype=np.int16)
    out = conv.convert(raw)
    out_arr = np.frombuffer(out, dtype=np.int16)
    expected_len = 4800
    _check("downsampled sample count ~ 1/3 of input", abs(len(out_arr) - expected_len) <= 2,
           f"got {len(out_arr)}, expected ~{expected_len}")


async def _test_mono_to_stereo() -> None:
    logger.info("--- mono -> stereo channel duplication ---")
    src_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    dst_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=2, sample_width=2)
    conv = AudioConverter(src_fmt, dst_fmt)
    raw = _make_tone(440, 0.02, 48000, channels=1, dtype=np.int16)
    out = conv.convert(raw)
    out_arr = np.frombuffer(out, dtype=np.int16).reshape(-1, 2)
    _check("stereo output has 2 channels", out_arr.shape[1] == 2)
    _check("both channels identical (duplicated mono)", np.array_equal(out_arr[:, 0], out_arr[:, 1]))


async def _test_stereo_to_mono() -> None:
    logger.info("--- stereo -> mono downmix (averaging) ---")
    src_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=2, sample_width=2)
    dst_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    conv = AudioConverter(src_fmt, dst_fmt)
    n = 960
    left = np.full(n, 10000, dtype=np.int16)
    right = np.full(n, -10000, dtype=np.int16)
    stereo = np.empty((n, 2), dtype=np.int16)
    stereo[:, 0], stereo[:, 1] = left, right
    raw = stereo.reshape(-1).tobytes()
    out = conv.convert(raw)
    out_arr = np.frombuffer(out, dtype=np.int16)
    _check("mono downmix of +10000/-10000 is ~0", np.allclose(out_arr, 0, atol=2), f"got mean={out_arr.mean()}")


async def _test_encoding_conversion() -> None:
    logger.info("--- encoding conversion int16 -> float32 ---")
    src_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    dst_fmt = AudioFormat(encoding=Encoding.PCM_F32LE, sample_rate=48000, channels=1, sample_width=4)
    conv = AudioConverter(src_fmt, dst_fmt)
    raw = _make_tone(440, 0.02, 48000, channels=1, dtype=np.int16)
    out = conv.convert(raw)
    out_arr = np.frombuffer(out, dtype=np.float32)
    _check("float32 output length correct", len(out) == 960 * 4, f"got {len(out)} bytes")
    _check("float32 values within [-1, 1]", out_arr.max() <= 1.0 and out_arr.min() >= -1.0)


async def _test_chunked_streaming() -> None:
    logger.info("--- chunked/streaming input with mid-sample splits (leftover buffering) ---")
    src_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    dst_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2,
                           container="raw")
    raw = _make_tone(880, 0.1, 48000, channels=1, dtype=np.int16)  # 4800 samples = 9600 bytes

    conv_chunked = AudioConverter(src_fmt, dst_fmt)
    reassembled = b""
    for piece in _chunk_bytes(raw, 7):  # 7-byte pieces guarantee mid-sample splits (itemsize=2)
        reassembled += conv_chunked.convert(piece)
    reassembled += conv_chunked.flush()

    _check(
        "reassembled length matches original despite odd chunking",
        len(reassembled) == len(raw) - (len(raw) % 2),
        f"got {len(reassembled)}, original {len(raw)}",
    )

    conv_single = AudioConverter(src_fmt, dst_fmt)
    single_shot = conv_single.convert(raw)
    arr_chunked = np.frombuffer(reassembled, dtype=np.int16)
    arr_single = np.frombuffer(single_shot, dtype=np.int16)
    min_len = min(len(arr_chunked), len(arr_single))
    _check(
        "chunked reassembly matches single-shot conversion sample-for-sample",
        np.array_equal(arr_chunked[:min_len], arr_single[:min_len]),
    )


async def _test_reset() -> None:
    logger.info("--- leftover state does not leak across reset() ---")
    fmt_a = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    fmt_b = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=44100, channels=1, sample_width=2)
    conv = AudioConverter(fmt_a, fmt_b)
    conv.convert(b"\x01")  # 1 odd byte, becomes leftover
    _check("leftover populated before reset", conv._leftover == b"\x01")
    conv.reset()
    _check("leftover cleared after reset", conv._leftover == b"")


async def _test_pcm_u8_roundtrip() -> None:
    logger.info("--- pcm_u8 -> pcm_s16le roundtrip (min/mid/max) ---")
    src_fmt = AudioFormat(encoding=Encoding.PCM_U8, sample_rate=48000, channels=1, sample_width=1)
    dst_fmt = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    conv = AudioConverter(src_fmt, dst_fmt)
    u8_raw = bytes([0, 128, 255])
    out = conv.convert(u8_raw)
    out_arr = np.frombuffer(out, dtype=np.int16)
    _check("u8=0 (min) maps to strongly negative int16", out_arr[0] < -30000, f"got {out_arr[0]}")
    _check("u8=128 (silence) maps near zero", abs(int(out_arr[1])) < 500, f"got {out_arr[1]}")
    _check("u8=255 (max) maps to strongly positive int16", out_arr[2] > 30000, f"got {out_arr[2]}")


async def _test_empty_input() -> None:
    logger.info("--- empty input returns empty output, no crash ---")
    fmt_a = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=48000, channels=1, sample_width=2)
    fmt_b = AudioFormat(encoding=Encoding.PCM_S16LE, sample_rate=44100, channels=1, sample_width=2)
    conv = AudioConverter(fmt_a, fmt_b)
    out = conv.convert(b"")
    _check("empty bytes in -> empty bytes out", out == b"")


async def _test() -> None:
    await _test_passthrough()
    await _test_upsample()
    await _test_downsample()
    await _test_mono_to_stereo()
    await _test_stereo_to_mono()
    await _test_encoding_conversion()
    await _test_chunked_streaming()
    await _test_reset()
    await _test_pcm_u8_roundtrip()
    await _test_empty_input()

    passed = sum(_results)
    total = len(_results)
    if all(_results):
        logger.info("RESULT: %d/%d checks passed", passed, total)
    else:
        logger.error("RESULT: %d/%d checks passed", passed, total)
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_test())