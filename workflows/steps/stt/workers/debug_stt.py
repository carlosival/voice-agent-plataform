import os
from .config import DEBUG_DIR
from workflows.utils import frames_to_mono_int16
from av import AudioFrame

async def debug_stt(frames: list[AudioFrame]) -> str:
                # Setup Debug Directory
                debug_dir = DEBUG_DIR
                os.makedirs(debug_dir, exist_ok=True)

                pcm = frames_to_mono_int16(frames)

                # 2. DEBUG LOGGING: Save the exact PCM sent to Whisper
                # We do this before the task so we have the file even if the task is cancelled
                filename = os.path.join(debug_dir, f"{uuid.uuid4().hex}_{len(frames)}frames.wav")
                try:
                    with wave.open(filename, "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(48000)   # Faster-Whisper standard
                        wf.writeframes(pcm.tobytes())
                    logger.info(f"STT debug saved: {filename} | samples={len(pcm)} | rms={np.sqrt(np.mean(pcm.astype(np.float32)**2)):.1f}")
                except Exception as e:
                    logger.error(f"STT Debug Save Failed: {e}")