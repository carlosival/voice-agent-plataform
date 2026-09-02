from .config import PRE_ROLL_LEN, MAX_UTTERANCE_LEN, SILERO_ACCUM
from workflows.signals import SignalFrame, WarmUp, AskUserStillThere
from workflows.utils import frames_to_mono_int16, silero_has_speech_from_numpy
from yaafpy.types import ExecContext
from av import AudioFrame
from typing import AsyncGenerator
from enum import Enum
from collections import deque
import logging

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════════
# Stage 1  –  VAD gate
# AudioFrame  →  list[AudioFrame]  (one complete utterance)
# Is Expecting Frames of 20ms with a sample rate of 16 KHz
# ════════════════════════════════════════════════════════════════════════════════

class VADState(Enum):
    QUIET    = 1
    STARTING = 2
    SPEAKING = 3
    STOPPING = 4

async def vad_gate(source: AsyncGenerator, ctx: ExecContext) -> AsyncGenerator[list[AudioFrame], None]:
    state          = VADState.QUIET
    starting_count = 0
    stopping_count = 0
    utterance_buf  = []      # grows unbounded during speech — no deque cap
    silero_buf     = []      # accumulates SILERO_ACCUM frames before VAD call
    consecutive_silence_counter = 0
    ask_user = 0
    
    # This holds audio history during silent periods
    pre_roll_history = deque(maxlen=PRE_ROLL_LEN)


    #yield WarmUp()  # agent greets user immediately

    async for frame in source:

        # Signal control frames
        if isinstance(frame, SignalFrame):
            if isinstance(frame, WarmUp):
                yield WarmUp()
                continue
            elif isinstance(frame, AskUserStillThere):
                yield AskUserStillThere()
                continue

        silero_buf.append(frame)

        pre_roll_history.append(frame) # Always track history

        if state in (VADState.STARTING, VADState.SPEAKING, VADState.STOPPING):
            utterance_buf.append(frame)

        if len(silero_buf) < SILERO_ACCUM:
            continue

        # Save before reset so QUIET→STARTING can backfill
        evaluated_frames = list(silero_buf)
        
        # Convert AudioFrames to 1D numpy array
        pcm = np.concatenate([
            frame.to_ndarray().reshape(-1)
            for frame in evaluated_frames
        ])
        confident = silero_has_speech_from_numpy(pcm)
        silero_buf = []

        if confident:
            match state:
                case VADState.QUIET:
                    state          = VADState.STARTING
                    starting_count = SILERO_ACCUM

                    # Instead of just starting fresh, we take the history
                    # This ensures Whisper hears the "H" in "Hello"
                    utterance_buf = list(pre_roll_history)
                    logger.debug(f"VAD: Start detected. Pre-roll added {PRE_ROLL_LEN} frames.")

                case VADState.STARTING:
                    starting_count += SILERO_ACCUM
                    if starting_count >= START_FRAMES:
                        logger.info(f"VAD: SPEAKING ({starting_count*20}ms of speech)")
                        state = VADState.SPEAKING
                        consecutive_silence_counter = 0
                        ask_user = 0
                        # SIGNAL 1: Tell everyone to SHUT UP right now
                        yield StartSpeaking()
                case VADState.SPEAKING:
                    pass
                case VADState.STOPPING:
                    state          = VADState.SPEAKING
                    stopping_count = 0
        else:
            match state:
                case VADState.QUIET:
                    consecutive_silence_counter += SILERO_ACCUM
                    # Check for hard stop (e.g., 120 seconds)
                    if consecutive_silence_counter >= INACTIVITY_STOP:
                        logger.info("VAD: Absolute inactivity limit reached. Closing pipeline.")
                        yield EndOfStream
                        return # This kills the generator
                    if ask_user < MAX_ASK_USER and consecutive_silence_counter >= INACTIVITY_FRAMES:
                        logger.info("VAD: Max silence between utterances reached. Reactivating.")
                        yield AskUserStillThere()
                        ask_user += 1
                case VADState.STARTING:
                    state          = VADState.QUIET
                    starting_count = 0
                    utterance_buf  = []
                case VADState.SPEAKING:
                    state          = VADState.STOPPING
                    stopping_count = SILERO_ACCUM
                case VADState.STOPPING:
                    stopping_count += SILERO_ACCUM
                    if stopping_count >= STOP_FRAMES:
                        logger.info(f"VAD: → {len(utterance_buf)} frames ({len(utterance_buf)*20}ms)")
                        state          = VADState.QUIET
                        # SIGNAL 3: User is done.
                        yield EndSpeaking()
                        # 4. NOW send the data
                        yield utterance_buf
                        utterance_buf  = []
                        starting_count = 0
                        stopping_count = 0
                        consecutive_silence_counter = 0