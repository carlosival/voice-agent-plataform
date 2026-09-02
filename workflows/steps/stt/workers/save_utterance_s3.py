'''
Save the audio frames to S3 Blob Storage
'''

from av import AudioFrame

async def save_s3(frames: list[AudioFrame]) -> str:
    pass