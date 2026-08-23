from workflows.steps.outputs.types import AudioFormat

WEBRTC_AUDIO_FORMAT = AudioFormat(
    encoding="pcm_s16le",
    sample_rate=48000,
    channels=1,
    container="raw",
    sample_width=2,
)

OPENAI_FORMAT = AudioFormat(
    encoding="pcm_s16le",
    sample_rate=24000,
    channels=1,
    container="raw",
    sample_width=2,
)

GROQ_AUDIO_FORMAT = AudioFormat(
    encoding="pcm_s16le",
    sample_rate=24000,
    channels=1,
    container="raw",
    sample_width=2,
)


TELNYX_AUDIO_FORMAT = AudioFormat(
    encoding="pcm_s16le",
    sample_rate=8000,
    channels=1,
    container="raw",
    sample_width=2,
)


def get_output_expect_format(output) -> AudioFormat:
    """
    Returns the expected audio format for the given output.
    """
    if isinstance(output, AudioOutputTrack):
        return WebRTCAudioFormat
    # Add other output types here
        