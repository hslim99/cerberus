import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import subprocess
import json

# yt-dlp 설정
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # ipv6 문제 방지
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


async def get_title_from_url_cli(url: str) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            "yt-dlp", "-j", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(stderr.decode().strip())

        data = json.loads(stdout)
        if "title" in data:
            return data["title"]
        elif "entries" in data and isinstance(data["entries"], list):
            return data["entries"][0].get("title", "알 수 없는 제목")
        else:
            return "알 수 없는 제목"
    except Exception as e:
        return f"(제목 추출 실패: {e})"


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []

    @app_commands.command(name="play", description="유튜브 링크로 음악을 재생합니다.")
    @app_commands.describe(url="유튜브 비디오 URL")
    async def play(self, interaction: discord.Interaction, url: str):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("먼저 음성 채널에 참가해주세요.", ephemeral=True)
            return

        if len(self.queue) >= 10:
            await interaction.response.send_message("대기열은 최대 10곡까지 가능합니다.", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if not vc or not vc.is_connected():
            vc = await voice_channel.connect()

        await interaction.response.defer()

        # 유튜브에서 제목 미리 가져오기
        try:
            title = await get_title_from_url_cli(url)
            self.queue.append((title, url))

            if not vc.is_playing():
                await self.play_next(vc, interaction)
            else:
                await interaction.followup.send(f"🎵 `{title}`을 재생 목록에 추가했어요!")
        except Exception as e:
            await interaction.followup.send(f"오류 발생: {e}", ephemeral=True)

    async def play_next(self, vc, interaction):
        def check_error(e):
            if e:
                print(f"플레이 중 오류 발생: {e}")
                asyncio.run_coroutine_threadsafe(interaction.followup.send(f"⚠️ 재생 중 오류 발생: {e}. 다음 곡으로 넘어갑니다."), self.bot.loop)
                self.bot.loop.create_task(self.play_next(interaction.guild.id))
        while self.queue:
            title, url = self.queue.pop(0)
            for attempt in range(5):
                try:
                    player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)

                    def after_play(err):
                        if err:
                            print(f"오류 발생: {err}")
                        if vc and vc.is_connected():
                            vc.stop()  # FFmpeg 프로세스 완전 종료
                            print("🎶 재생이 종료되었습니다.")

                    vc.play(player, after=lambda e: check_error(e) if e else self.bot.loop.create_task(self.play_next(vc, interaction)))
                    await interaction.followup.send(f"🎶 재생 중: **{title}**")
                    return
                except Exception as e:
                    if attempt < 4:
                        await asyncio.sleep(3)
                    else:
                        await interaction.followup.send(f"오류 발생: {e}")

    @app_commands.command(name="queue", description="현재 대기열을 확인합니다.")
    async def queue_command(self, interaction: discord.Interaction):
        if not self.queue:
            await interaction.response.send_message("🎵 대기열이 비어 있습니다.")
            return

        display = ""
        for i, (title, _) in enumerate(self.queue[:10]):
            display += f"{i+1}. {title}\n"
        await interaction.response.send_message(f"🎶 현재 대기열:\n{display}")

    @app_commands.command(name="remove", description="대기열에서 특정 곡을 제거합니다.")
    @app_commands.describe(index="제거할 곡 번호 (1부터 시작)")
    async def remove_command(self, interaction: discord.Interaction, index: int):
        if index < 1 or index > len(self.queue):
            await interaction.response.send_message("❌ 유효하지 않은 번호입니다.", ephemeral=True)
            return
        title, url = self.queue.pop(index - 1)
        await interaction.response.send_message(f"🗑️ `{title}`을 대기열에서 제거했어요.")

    @app_commands.command(name="leave", description="봇을 음성 채널에서 나가게 합니다.")
    async def leave(self, interaction: discord.Interaction):
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if not vc or not vc.is_connected():
            await interaction.response.send_message("봇이 음성 채널에 있지 않습니다.", ephemeral=True)
            return
        await vc.disconnect()
        await interaction.response.send_message("👋 음성 채널에서 나왔습니다.")


async def init_music(bot):
    await bot.add_cog(Music(bot))
