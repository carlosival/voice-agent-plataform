import asyncio
from typing import Any
from yaafpy import ExecContext


'''
This middleware is responsable to handle the LLM stream response.
And how the response is accumulated and sent to next middleware.
The next middleware could be a decision node to decide if the agent should execute a tool, run a code
or just pass the answer downstream. 
'''
async def llm_sink_res(
    input_data: asyncio.Queue,
    ctx:    ExecContext,
) -> None:

    queue = input_data
    timeout_limit = 5.0
    task = None

    try:
        while True:
            # 1. WAIT WITH TIMEOUT
            # If LLM doesn't yield a sentence in 5s, send a placeholder
            event = await queue.get()
            if event is None:
                break
            
    except asyncio.TimeoutError:
        logger.error("[LLM Stream] Timeout waiting for LLM response.")
    finally:
        await task  # ensure task completes and exceptions propagate