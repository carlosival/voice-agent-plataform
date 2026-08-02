from workflows.steps.llm.types import LLMEvent


'''
    This layer send all info the llm needs, prompt,tools, messages, etc 
    and handle all type of response's tokens, content, tools_call, reasoning, etc.
    How to setup and handle the response is tight coupling with the LLM Provider.
    
    token event will be yield for each token.
    tool_call event will be yield when the llm finish the response.?
    finish event will be yield when the llm finish the response.
    reasoning event will be yield when the llm finish the response.
    coding_block event will be yield when the llm finish the response.
    ttft event will be yield when the llm finish the response.
    token_usage event will be yield when the llm finish the response.
'''
async def call_llm_stream_openai(
    messages: Optional[list] = None,
    tools: Optional[list] = None,
    http_client: Optional[AsyncClient] = None,
    tracing_data: Optional[dict] = None,
    model: Optional[str] = None,
    prompt: Optional[str] = None,
    provider_url: str = None,
    api_key: str = None,
    llm_config: Optional[dict] = {},
) -> AsyncGenerator[LLMEvent, None]:
    """
    Async streaming using AsyncOpenAI client style.
    Yields LLMEvent with event: 'token' | 'tool_call' | 'finish' | 'reasoning'.

    Also Yields custom events: coding_block, ttft (time to first token), token_usage, etc.
    Handle more as needed.
    """
    if http_client is None:
        http_client = AsyncClient(timeout=30.0)
    
    if prompt and (messages or tools):
        logger.warning("[LLM Engine] Prompt and messages or tools provided.")
        # TODO: Handle this case do something more stream like raise a exception or yield a error event

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=provider_url,
        http_client=http_client
    )
    kwargs = {
        "model": model,
        "stream": True,
    }

    if prompt:
        kwargs["prompt"] = prompt
    
    if messages:
        kwargs["messages"] = messages    

    if tools and len(tools) > 0:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    if llm_config:
        kwargs.update(llm_config)

    # --- MINIMAL TRACING HOOKS ---
    tracer = tracing_data.get("tracer") if tracing_data else None
    trace_id = tracing_data.get("trace_id") if tracing_data else None
    parent_span_id = tracing_data.get("parent_span_id") if tracing_data else None
    span = None

    if tracer and trace_id:

        # Build a complete input object containing both messages and available tools or prompt
        trace_input = {}
        if messages:
            trace_input["messages"] = messages
        if prompt:
            trace_input["prompt"] = prompt
        if tools:
            trace_input["tools"] = tools  # <-- Pass the available tools here

        # Refactor this to get more data like TTFT, Token Usage, etc.
        span = tracer.start_observation(
            name="llm_stream_generation",
            as_type="generation",
            model=model,
            input=trace_input,
            trace_context={"trace_id": trace_id, "parent_span_id": parent_span_id}  # Links cleanly as a child under the WebRTC session
        )

    accumulated_text = "" # Only for debug pourposes yield individual token
    # Track accumulated tool calls by their delta index
    accumulated_tools = {}
    final_reason = "unknown"

    try:
        async with await client.chat.completions.create(**kwargs) as stream:
            async for chunk in stream:
                logger.info(f"[raw_chunk] got chunk: {chunk}")  
                choice = chunk.choices[0]
                delta = choice.delta
                finish_reason = choice.finish_reason

                # ADD THIS:
                logger.info(f"[raw_chunk] finish={finish_reason} content={repr(getattr(delta, 'content', None))} tool_calls={getattr(delta, 'tool_calls', None)}")

                # Extract content and tool, calls, could be reasoning, etc from the delta
                token = getattr(delta, "content", None)
                tool_calls = getattr(delta, "tool_calls", None) or []

                if token:
                    accumulated_text += token
                    yield {"event": "token", "data": token}

                for tc in tool_calls:

                    idx = tc.index
                    
                    # 1. Initialize the tool slot if it's the first time seeing this index
                    if idx not in accumulated_tools:
                        accumulated_tools[idx] = {
                            "id": tc.id, # Sent in the first chunk for this index
                            "name": tc.function.name if tc.function else "",
                            "arguments": ""
                        }
                    
                    # 2. Update properties if they are sent in subsequent chunks
                    if tc.id and not accumulated_tools[idx]["id"]:
                        accumulated_tools[idx]["id"] = tc.id
                    if tc.function and tc.function.name:
                        accumulated_tools[idx]["name"] = tc.function.name
                        
                    # 3. Accumulate the streamed JSON arguments string
                    if tc.function and tc.function.arguments:
                        accumulated_tools[idx]["arguments"] += tc.function.arguments


                    yield   {
                                "event": "tool_call",
                                "data": {
                                    "index": tc.index,
                                    "id": tc.id,
                                    "function": {
                                        "name": tc.function.name if tc.function else "",
                                        "arguments": tc.function.arguments if tc.function else "",
                                    },
                                }
                            }

                if finish_reason:
                    yield {"event": "finish", "data": finish_reason}
        
        # Convert our tracking dict back into a clean list for the tracer
        final_tools = [tool for idx, tool in sorted(accumulated_tools.items())]

        # Stream ended cleanly -> update output data
        if span:
            span.update(output={"text": accumulated_text, "tool_calls": final_tools, "finish_reason": final_reason})
    except asyncio.CancelledError:
        # User barged in and interrupted the stream
        logger.info("[LLM Engine] Stream cut short by user barge-in.")
        if span:
            span.update(
                level="WARNING",
                status_message="Stream dropped due to user interruption event.",
                output={"text": accumulated_text + "... [Cut Off]","tool_calls": final_tools, "finish_reason": "barge_in"}
            )
        raise  # Must re-raise CancelledError for proper pipeline task cleanup
    except Exception as e:
        logger.error(f"Error calling LLM: {e}")
        if span:
            span.update(level="ERROR", status_message=str(e))
    finally:
        if span:
            span.end()