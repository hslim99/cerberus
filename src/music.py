import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio

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
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)


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

    @app_commands.command(name="play", description="유튜브 링크로 음악을 재생합니다.")
    @app_commands.describe(url="유튜브 비디오 URL")
    async def play(self, interaction: discord.Interaction, url: str):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("먼저 음성 채널에 참가해주세요.", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if not vc or not vc.is_connected():
            vc = await voice_channel.connect()

        try:
            await interaction.response.defer()
            player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
            vc.play(player, after=lambda e: print(f'플레이 종료: {e}') if e else None)
            await interaction.followup.send(f"🎶 재생 중: **{player.title}**")
        except Exception as e:
            await interaction.followup.send(f"오류 발생: {e}")

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
