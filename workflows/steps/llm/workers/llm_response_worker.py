import asyncio
from typing import Optional
from httpx import AsyncClient

async def llm_stream_openai_worker(
    input_queue: asyncio.Queue,
    ctx: ExecContext,
    output_queue: asyncio.Queue
    ):

    tool_calls_acc: dict[int, dict] = {}


    try:
        while True:
            
            event = await input_queue.get()
            event_type = event.event
            event_data = event.data
            
            if event_type == "token":
                pass

            if event_type == "tool_call":
                pass
                

            if event_type == "error":
                pass

            if event_type == "coding":
                pass
                
            # ─────────────────────────────────────────────
            # FINISH HANDLING
            # ─────────────────────────────────────────────    
            if event_type == "finish":
                reason = event_data

                logger.info(
                    f"[llm_stream] finish reason: {reason}"
                )

                if reason == "tool_calls":

                    tool_calls_mapped = [
                        ToolCallChunk(
                            id=acc["id"],
                            name=acc["name"],
                            arguments=acc["arguments"],
                        )
                        for acc in tool_calls_acc.values()
                    ]

                    logger.info(
                        f"[llm_stream] Reduced tool calls: {tool_calls_mapped}"
                    )   

                    # Always put a LIST, never a bare ToolCallChunk
                    assert isinstance(tool_calls_mapped, list) 
                    output_queue.put_nowait(tool_calls_mapped)

                    tool_calls_acc.clear()

            if event is None:
                break
            
    except asyncio.TimeoutError:
        logger.error("[LLM Stream] Timeout waiting for LLM response.")
    finally:
        await task  # ensure task completes and exceptions propagate