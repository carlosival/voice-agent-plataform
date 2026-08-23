
    
# 3. DEFINE THE SYNTHESIS WORKER
async def tts_worker(client: httpx.AsyncClient, 
                        output_track, 
                        tts_queue, 
                        provider_name: str
                        queue
                        **kwargs
                    ):
        while True:
            try:
                text = await tts_queue.get()
                if text is None:
                    break
                
                # get a payload  
                payload = {}  
                frame_count = 0
                
                async for chunk_bytes in call_tts_stream(http_client=http_client, text=text, debug=True):
                    source_chunk = AudioFrame.from_bytes(chunk_bytes, format=TWILIO_FORMAT)
                    if converter is None:
                        converter = StatefulAudioConverter(
                            source_format=source_chunk.format,
                            target_format=TWILIO_FORMAT,
                        )

                    destination_chunk = converter.convert(source_chunk)
                    
                
                if frame_count > 0:
                    await track.add_silence(duration_frames=20)
                    logger.info(f"TTS Worker: Finished {frame_count} frames for: {text}")
                
            except CancelledError:
                # Still vital for barge-in!
                logger.debug("TTS Worker: Cancelled (Barge-in).")
                raise 
            except Exception as e:
                logger.error(f"TTS Worker Error: {e}")

    
    # 1. Warm up the track for first time
    #await output_track.add_silence(duration_frames=15)

    current_task = create_task(tts_worker(http_client, output_track))

    try:
        async for sentence in source:
            if isinstance(sentence, WarmUp):
                logger.info(f"TTS received WarmUp signal.")
                await output_track.add_silence(duration_frames=50)
                await tts_queue.put("¡Hola! ¿Cómo puedo ayudarte?")

            if isinstance(sentence, EndOfStream):
                logger.info("TTS: EndOfStream received. Cleaning up.")
                # Optional: Send a goodbye message before killing
                await wait_for(tts_queue.put("¡Hasta luego!"), timeout=2.0) 
                await wait_for(tts_queue.put(None), timeout=2.0)
                break
            # 1. SIGNAL HANDLING (The "Kill Switch")
            if isinstance(sentence, StartSpeaking):
                logger.info("[AUDIO_KILL] TTS received StartSpeaking. Purging output track.")
                # Clear pending sentences
                while not tts_queue.empty():
                    tts_queue.get_nowait()
                # Cancel whatever is currently synthesizing
                if current_task and not current_task.done():
                    current_task.cancel()
                    try:
                        await current_task
                    except CancelledError:
                        pass
                output_track.purge()
                # Restart the sequential worker
                current_task = create_task(tts_worker(http_client, output_track))
                continue

            # 2. DATA HANDLING (The Sentence)
            if isinstance(sentence, str):
                logger.info(f"TTS received sentence: '{sentence}'")
                await wait_for(tts_queue.put(sentence), timeout=2.0)
            
            # 3. ASK USER STILL THERE
            if isinstance(sentence, AskUserStillThere):
                logger.info("TTS received AskUserStillThere signal.")
                if tts_queue.empty():
                    await wait_for(tts_queue.put("¿Te puedo ayudar en algo más?"), timeout=2.0)
            
    except Exception as e:
        logger.error(f"TTS Main Loop Exception: {e}")
        raise
    finally:
        await wait_for(tts_queue.put(None), timeout=2.0)  # shutdown sentinel
        if current_task and not current_task.done():
            current_task.cancel()
        # This is critical for yaafpy
        raise WorkflowAbortException("End of stream.")

    if False: yield  # ← makes Python treat this as an async generator function 

