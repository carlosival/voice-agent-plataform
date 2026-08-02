import asyncio
from typing import Any
from yaafpy import ExecContext
from workflows.utils.tools import ToolCallChunk, CodeChunk

'''
This middleware is responsable to handle the LLM stream response.
Should decide if the agent should execute a tool, run a code
or just pass the answer downstream.
'''
async def route_llm_response(
    input_data: asyncio.Queue,
    ctx:    ExecContext,
) -> None:

    streaming = False
    
    while True:
        value = await input_data.get()
        
        if value is list[ToolCallChunk]:
            ctx.jump_to("execute_tool")
            return value, ctx
        
        if value is str:
            if ctx.shared_data["stream"]:
                out_queue.put_nowait(value) 
                if not streaming: # return a async generator from the queue
                    streaming = True
                    out_queue = asyncio.Queue()
                    async def gen():
                        while True:
                            item = await out_queue.get()
                            if item is None:  # define a real sentinel
                                out_queue.put_nowait(None)
                                break
                            yield item
                        
                    yield gen , ctx
                continue
            else:
                return value, ctx
                
        if value is CodeChunk:
            ctx.jump_to("execute_code")
            return value, ctx
        if value is None:
            break
    
