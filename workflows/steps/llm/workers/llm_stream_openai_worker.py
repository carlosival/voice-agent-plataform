import asyncio
from typing import Optional
from httpx import AsyncClient

async def llm_stream_openai_worker(
    messages: Optional[list] = None,
    tools: Optional[list] = None,
    http_client: Optional[AsyncClient] = None,
    tracing_data: Optional[dict] = None,
    model: Optional[str] = None,
    prompt: Optional[str] = None,
    provider_url: str = None,
    api_key: str = None,
    llm_config: Optional[dict] = {},
    queue: asyncio.Queue = None
    ):

    async for event in call_llm_stream_openai(
                messages=messages,
                tools=tools,
                http_client=http_client,
                tracing_data=tracing_data,
                model=model,
                prompt=prompt,
                provider_url=provider_url,
                api_key=api_key,
                llm_config=llm_config,
                ):
                
                queue.put_nowait(event)