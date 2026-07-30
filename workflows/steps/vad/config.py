PRE_ROLL_LEN = 50
MAX_UTTERANCE_LEN = 1000 # 1000frames * 20ms = 20min; Hold the max length of the audio conversation

QUEUE_BACKPRESSURE_MAXSIZE = 10

# Tunable thresholds in real time
START_SECS   = 0.2   # confirmed speech after this long
STOP_SECS    = 0.6   # confirmed silence after this long
FRAME_SECS   = 0.02  # 20ms per aiortc frame
INACTIVITY_SECS = 60 # 60 seconds At this point the agent will ask the user still there?

START_FRAMES = round(START_SECS / FRAME_SECS)   # 10 frames
STOP_FRAMES  = round(STOP_SECS  / FRAME_SECS)   # 40 frames
INACTIVITY_FRAMES = round(INACTIVITY_SECS / FRAME_SECS) # 60 seconds At this point the agent will ask the user still there?
INACTIVITY_STOP = 2 * INACTIVITY_FRAMES
MAX_ASK_USER = 1
SILERO_ACCUM = 3                                 # frames to accumulate before Silero call
                                                 # 3 × 320 = 960 samples > 512 min ✓

SAMPLE_RATE     = 16_000
VAD_WINDOW_SIZE      = 50          # frames per VAD call  (~1 s @ 20 ms/frame)
VAD_SILENCE_WINDOWS_LIMIT = 3      # silent windows after speech → flush utterance
VAD_THRESHOLD   = 0.5
VAD_STRIDE    = 10  # call VAD every 20 frames -> call every 400ms
