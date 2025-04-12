import asyncio

yt_dlp_semaphore = asyncio.Semaphore(2)
ffmpeg_semaphore = asyncio.Semaphore(2)
