
    
# 3. DEFINE THE SYNTHESIS WORKER
async def tts_worker(client: httpx.AsyncClient, 
                        output_track, 
                        tts_queue, 
                        provider_name: str,
                        **kwargs
                    ):
        
        converter = StatefulAudioConverter(
                            source_format=get_stt_provider_format(provider_name),
                            target_format=get_output_format(output_track),
                        )
        while True:
            try:
                text = await tts_queue.get()
                if text is None:
                    # flush the converter or padding the converter with silence to make sure the last chunk is not lost
                    # send to the output track
                    #output_track.add_audio(converter.flush())
                    
                    break
                
                # get a payload  
                payload = {}  
                frame_count = 0
                
                async for chunk_bytes in call_tts_stream(http_client=http_client, text=text, debug=True):
                    # I don't really need to convert the bytes to an AudioFrame
                    # I can just add the bytes directly to the output track
                    # But I need to make sure the format is correct
                    # The format is PCM_S16LE at 24000 Hz
                    # The output track is PCM_S16LE at 8000 Hz
                    # So I need to convert the format
                    #source_chunk = AudioFrame.from_bytes(chunk_bytes, format=TWILIO_FORMAT)

                    destination_chunk = converter.convert(chunk_bytes)
                    output_track.add_audio(destination_chunk)
                    
                
                if frame_count > 0:
                    await track.add_silence(duration_frames=20)
                    logger.info(f"TTS Worker: Finished {frame_count} frames for: {text}")
                
            except CancelledError:
                # Still vital for barge-in!
                logger.debug("TTS Worker: Cancelled (Barge-in).")
                raise 
            except Exception as e:
                logger.error(f"TTS Worker Error: {e}")

    
