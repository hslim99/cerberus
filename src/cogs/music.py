import asyncio
import json

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from utils.cookie import TemporaryCookie
from utils.ytdl import ffmpeg_options, get_ytdl_options

load_dotenv()


async def get_title_from_url_cli(url: str) -> str:
    try:
        with TemporaryCookie() as cookiefile:
            cmd = ["yt-dlp"]
            if cookiefile:
                cmd += ["--cookies", cookiefile]
            cmd += ["-j", url]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
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
        print(f"(제목 추출 실패: {e})")
        return url


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, options, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.options = options
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = asyncio.get_event_loop()

        with TemporaryCookie() as cookiefile:
            options = get_ytdl_options(cookiefile)

            def extract():
                print("[DEBUG] cookiefile:", options.get("cookiefile"))
                with yt_dlp.YoutubeDL(options) as ydl:
                    data = ydl.extract_info(url, download=not stream)
                    return data["entries"][0] if "entries" in data else data

            data = await loop.run_in_executor(None, extract)

            filename = (
                data["url"]
                if stream
                else yt_dlp.YoutubeDL(options).prepare_filename(data)
            )
            return cls(
                discord.FFmpegPCMAudio(filename, **ffmpeg_options),
                data=data,
                options=options,
            )


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue = []
        self.current = None
        self.force_stop = False
        self.playing_task = False

    async def leave_channel(
        self, guild: discord.Guild, interaction: discord.Interaction = None
    ):
        vc = discord.utils.get(self.bot.voice_clients, guild=guild)
        if not vc or not vc.is_connected():
            return

        if vc.is_playing():
            vc.stop()
            await asyncio.sleep(0.3)

        self.queue.clear()
        self.current = None
        self.force_stop = True

        await vc.disconnect()
        if interaction:
            await interaction.response.send_message("👋 음성 채널에서 나왔습니다.")

    async def check_and_leave_if_alone(
        self, guild: discord.Guild, channel: discord.VoiceChannel
    ):
        print("확인 중...")
        await asyncio.sleep(10)

        vc = discord.utils.get(self.bot.voice_clients, guild=guild)
        if not vc or not vc.is_connected():
            return

        if vc.channel != channel:
            return

        members = [m for m in channel.members if not m.bot]
        if len(members) == 0:
            await self.leave_channel(guild)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        if before.channel and before.channel != after.channel:
            vc = discord.utils.get(self.bot.voice_clients, guild=member.guild)
            if vc and vc.channel == before.channel:
                self.bot.loop.create_task(
                    self.check_and_leave_if_alone(member.guild, before.channel)
                )

    @app_commands.command(name="play", description="유튜브 링크로 음악을 재생합니다.")
    @app_commands.describe(url="유튜브 비디오 URL")
    async def play(self, interaction: discord.Interaction, url: str):
        self.force_stop = False
        self.playing_task = True

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                "먼저 음성 채널에 참가해주세요.", ephemeral=True
            )
            return

        if len(self.queue) >= 10:
            await interaction.response.send_message(
                "대기열은 최대 10곡까지 가능합니다.", ephemeral=True
            )
            return

        voice_channel = interaction.user.voice.channel
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if not vc or not vc.is_connected():
            vc = await voice_channel.connect()

        await interaction.response.defer()

        try:
            title = await get_title_from_url_cli(url)
            self.queue.append((title, url))

            if not vc.is_playing():
                await self.play_next(vc, interaction)
            else:
                await interaction.followup.send(
                    f"🎵 `{title}`을 재생 목록에 추가했어요!"
                )
        except Exception as e:
            await interaction.followup.send(f"오류 발생: {e}", ephemeral=True)
        finally:
            self.playing_task = False

    async def play_next(self, vc, interaction):
        while self.queue:
            if self.force_stop:
                return

            title, url = self.queue.pop(0)
            self.current = (title, url)
            for attempt in range(5):
                try:
                    player = await YTDLSource.from_url(
                        url, loop=self.bot.loop, stream=True
                    )

                    def after_play(err):
                        if self.force_stop:
                            return
                        if err:
                            print(f"오류 발생: {err}")
                            asyncio.run_coroutine_threadsafe(
                                interaction.followup.send(
                                    f"⚠️ 재생 중 오류 발생: {err}. 다음 곡으로 넘어갑니다."
                                ),
                                self.bot.loop,
                            )
                        self.bot.loop.create_task(self.play_next(vc, interaction))

                    vc.play(player, after=after_play)
                    await interaction.followup.send(f"🎶 재생 중: **{title}**")
                    return
                except Exception as e:
                    if attempt < 4:
                        await asyncio.sleep(3)
                    else:
                        await interaction.followup.send(f"오류 발생: {e}")
        if not self.queue and not self.playing_task:
            await self.leave_channel(interaction.guild)

    @app_commands.command(name="skip", description="현재 재생 중인 곡을 스킵합니다.")
    async def skip(self, interaction: discord.Interaction):
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if not vc or not vc.is_connected():
            await interaction.response.send_message(
                "봇이 음성 채널에 있지 않습니다.", ephemeral=True
            )
            return

        if not vc.is_playing():
            await interaction.response.send_message(
                "현재 재생 중인 곡이 없습니다.", ephemeral=True
            )
            return

        await interaction.response.send_message("⏭️ 현재 곡을 스킵했어요!")
        vc.stop()

    @app_commands.command(name="queue", description="현재 대기열을 확인합니다.")
    async def queue_command(self, interaction: discord.Interaction):
        now_playing = self.get_now_playing_text() + "\n\n"

        if not self.queue:
            await interaction.response.send_message(
                f"{now_playing}🎵 대기열이 비어 있습니다."
            )
            return

        display = ""
        for i, (title, url) in enumerate(self.queue[:10]):
            display += f"{i + 1}. [{title}]({url})\n"
        await interaction.response.send_message(
            f"{now_playing}🎶 현재 대기열:\n{display}"
        )

    @app_commands.command(name="remove", description="대기열에서 특정 곡을 제거합니다.")
    @app_commands.describe(index="제거할 곡 번호 (1부터 시작)")
    async def remove_command(self, interaction: discord.Interaction, index: int):
        if index < 1 or index > len(self.queue):
            await interaction.response.send_message(
                "❌ 유효하지 않은 번호입니다.", ephemeral=True
            )
            return
        title, url = self.queue.pop(index - 1)
        await interaction.response.send_message(
            f"🗑️ `[{title}]({url})`을 대기열에서 제거했어요."
        )

    @app_commands.command(name="leave", description="봇을 음성 채널에서 나가게 합니다.")
    async def leave(self, interaction: discord.Interaction):
        await self.leave_channel(interaction.guild, interaction)

    def get_now_playing_text(self):
        if self.current:
            title, url = self.current
            return f"🎶 현재 재생 중: **[{title}]({url})**"
        else:
            return "현재 재생 중인 곡이 없습니다."

    @app_commands.command(
        name="nowplaying", description="현재 재생 중인 곡을 표시합니다."
    )
    async def nowplaying(self, interaction: discord.Interaction):
        text = self.get_now_playing_text()
        await interaction.response.send_message(text)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
