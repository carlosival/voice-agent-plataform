import logging
from workflows.steps.outputs import AudioConverter, get_stt_provider_format, get_output_format
from workflows.steps.tts.utils import call_tts_stream

    
# 3. DEFINE THE SYNTHESIS WORKER
async def tts_worker(client: httpx.AsyncClient, 
                        output_track, 
                        tts_queue, 
                        provider_name: str,
                        **kwargs
                    ):
        
        converter = AudioConverter(
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
                    await output_track.push_pcm(destination_chunk)

                # End of TTS stream
                pcm = converter.flush()

                if pcm:
                    await output_track.push_pcm(pcm)
                        
            except CancelledError:
                # Still vital for barge-in!
                logger.debug("TTS Worker: Cancelled (Barge-in).")
                raise 
            except Exception as e:
                logger.error(f"TTS Worker Error: {e}")

    
