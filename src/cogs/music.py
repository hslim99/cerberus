import asyncio
import json
import re
import time
from typing import Tuple, Optional

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from utils.cookie import TemporaryCookie
from utils.message import send_message
from utils.ytdl import ffmpeg_options, get_ytdl_options

load_dotenv()

MAX_MIN = 30


async def get_metadata_from_url_cli(url: str):
    try:
        print("메타데이터 추출 중...")
        start = time.perf_counter()

        with TemporaryCookie() as cookiefile:
            cmd = [
                "yt-dlp",
                "--no-check-certificate",
                "--skip-download",
                "--no-playlist",
            ]
            if cookiefile:
                cmd += ["--cookies", cookiefile]
            cmd += ["-j", url]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            elapsed = int((time.perf_counter() - start) * 1000)
            print(f"메타데이터 추출 완료 (소요 시간: {elapsed}ms)")

            if process.returncode != 0:
                raise Exception(stderr.decode().strip())

            data = json.loads(stdout)
            return data["entries"][0] if "entries" in data else data
    except Exception as e:
        print(f"(메타데이터 추출 실패: {e})")
        return None


async def get_metadata_from_url_api(url: str):
    try:
        print("메타데이터 추출 중...")
        start = time.perf_counter()

        with TemporaryCookie() as cookiefile:
            options = get_ytdl_options(cookiefile)
            options.update(
                {
                    "skip_download": True,
                    "noplaylist": True,
                    "no_check_certificate": True,
                    "quiet": True,
                    "no_warnings": True,
                }
            )

            def extract():
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return info["entries"][0] if "entries" in info else info

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, extract)

            elapsed = int((time.perf_counter() - start) * 1000)
            print(f"메타데이터 추출 완료... (소요 시간: {elapsed}ms)")
            return data

    except Exception as e:
        print(f"메타데이터 추출 실패: {e}")
        return {}


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, options, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.options = options
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, data=None):
        print("영상 재생 초기화 중...")
        start = time.perf_counter()

        loop = asyncio.get_event_loop()

        try:
            with TemporaryCookie() as cookiefile:
                options = get_ytdl_options(cookiefile)

                def extract():
                    if data:
                        return data
                    print("[DEBUG] cookiefile:", options.get("cookiefile"))
                    with yt_dlp.YoutubeDL(options) as ydl:
                        _data = ydl.extract_info(url, download=not stream)
                        return _data["entries"][0] if "entries" in _data else _data

                data = await loop.run_in_executor(None, extract)

                filename = (
                    data["url"]
                    if stream
                    else yt_dlp.YoutubeDL(options).prepare_filename(data)
                )

                elapsed = int((time.perf_counter() - start) * 1000)
                print(f"영상 재생 초기화 완료 (소요 시간: {elapsed}ms)")

                return cls(
                    discord.FFmpegPCMAudio(filename, **ffmpeg_options),
                    data=data,
                    options=options,
                )
        except Exception as e:
            print(f"오류 발생: {e}")


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue = []
        self.current = None
        self.force_stop = False
        self.playing_task = False
        self.leave_task: Optional[asyncio.Task] = None

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
            await send_message(interaction, "👋 음성 채널에서 나왔습니다.")

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

    @staticmethod
    def has_permission(
        interaction: discord.Interaction,
        music: Tuple[str, str, int, dict],
        vc: discord.VoiceClient,
    ):
        _, _, request_user_id, _ = music
        if interaction.user.guild_permissions.manage_guild:
            return True
        if interaction.user.id == request_user_id:
            return True
        vc_member_ids = [member.id for member in vc.channel.members]
        if request_user_id not in vc_member_ids:
            return True
        return False

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

        voice_channel = interaction.user.voice.channel
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if not interaction.user.voice or not interaction.user.voice.channel:
            await send_message(
                interaction, "⚠️ 먼저 음성 채널에 참가해주세요.", ephemeral=True
            )
            return

        if vc and vc.is_connected():
            user_channel = interaction.user.voice.channel if interaction.user.voice else None
            if user_channel and vc.channel != user_channel:
                if self.current:
                    await send_message(
                        interaction, "⚠️ 봇이 이미 다른 채널에 있어요.", ephemeral=True
                    )
                    return
                else:
                    await vc.disconnect()
                    vc = await voice_channel.connect()

        if len(self.queue) >= 10:
            await send_message(
                interaction, "⚠️ 대기열은 최대 10곡까지 가능합니다.", ephemeral=True
            )
            return

        p = re.compile(r"^(https?://)?(www\.|m\.)?(youtube\.com|youtu\.be)/.+$")
        if not p.match(url):
            await send_message(
                interaction, "❌ 유효한 YouTube URL이 아닙니다.", ephemeral=True
            )
            return

        if not vc or not vc.is_connected():
            vc = await voice_channel.connect()

        if self.leave_task and not self.leave_task.done():
            self.leave_task.cancel()
            try:
                await self.leave_task
            except asyncio.CancelledError:
                pass
        self.leave_task = None

        await interaction.response.defer()

        try:
            get_from_cli = vc.is_playing()
            if get_from_cli:
                data = await get_metadata_from_url_cli(url)
            else:
                data = await get_metadata_from_url_api(url)
            title = data["title"] or url
            is_live = data["is_live"]
            duration = int(data["duration"])

            if is_live:
                await send_message(
                    interaction, "❌ 라이브 영상은 추가할 수 없어요.", ephemeral=True
                )
                return

            if duration and duration >= (60 * MAX_MIN):
                await send_message(
                    interaction,
                    f"❌ {MAX_MIN}분 미만의 영상만 재생할 수 있어요.",
                    ephemeral=True,
                )
                return

            self.queue.append(
                (title, url, interaction.user.id, data if not get_from_cli else None)
            )

            if (
                not vc.is_playing()  # To resolve the race condition, recall is_playing() again
            ):
                await self.play_next(vc, interaction)
            else:
                await send_message(
                    interaction,
                    f"🎵 [{title}]({url})을 재생 목록에 추가했어요!",
                    followup=True,
                )
        except Exception as e:
            await send_message(
                interaction, f"⚠️ 오류 발생: {e}", followup=True, ephemeral=True
            )
        finally:
            self.playing_task = False

    async def play_next(self, vc, interaction):
        while self.queue:
            if self.force_stop:
                return

            title, url, requested_user_id, data = self.queue.pop(0)
            self.current = (title, url, requested_user_id, data)
            for attempt in range(5):
                try:
                    player = await YTDLSource.from_url(
                        url, loop=self.bot.loop, stream=True, data=data
                    )

                    def after_play(err):
                        if self.force_stop:
                            return
                        if err:
                            print(f"오류 발생: {err}")
                            asyncio.run_coroutine_threadsafe(
                                send_message(
                                    interaction,
                                    f"⚠️ 재생 중 오류 발생: {err}. 다음 곡으로 넘어갑니다.",
                                    followup=True,
                                ),
                                self.bot.loop,
                            )
                        self.bot.loop.create_task(self.play_next(vc, interaction))

                    vc.play(player, after=after_play)
                    await send_message(
                        interaction,
                        f"🎶 재생 중: **[{title}]({url})**",
                        followup=True,
                    )
                    return
                except Exception as e:
                    if attempt < 4:
                        await asyncio.sleep(3)
                    else:
                        await send_message(
                            interaction, f"오류 발생: {e}", followup=True
                        )
        if not self.queue and not self.playing_task:
            self.current = None
            self.leave_task = asyncio.create_task(self.wait_and_leave(interaction.guild))
            # await self.leave_channel(interaction.guild)

    async def wait_and_leave(self, guild):
        wait_sec = 120
        try:
            await asyncio.sleep(wait_sec)
            if not self.queue and not self.current:
                await self.leave_channel(guild)
        except asyncio.CancelledError:
            pass
        self.leave_task = None

    @app_commands.command(name="skip", description="현재 재생 중인 곡을 스킵합니다.")
    async def skip(self, interaction: discord.Interaction):
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)

        if not vc or not vc.is_connected():
            await send_message(
                interaction, "⚠️ 봇이 음성 채널에 있지 않습니다.", ephemeral=True
            )
            return

        if not vc.is_playing():
            await send_message(
                interaction, "❌ 현재 재생 중인 곡이 없습니다.", ephemeral=True
            )
            return

        if Music.has_permission(interaction, self.current, vc):
            await send_message(interaction, "⏭️ 현재 곡을 스킵했어요!")
            vc.stop()
        else:
            await send_message(interaction, "❌ 해당 곡을 스킵할 권한이 없어요.")

    @app_commands.command(name="queue", description="현재 대기열을 확인합니다.")
    async def queue_command(self, interaction: discord.Interaction):
        now_playing = self.get_now_playing_text() + "\n\n"

        if not self.queue:
            await send_message(
                interaction,
                f"{now_playing}🎵 대기열이 비어 있습니다.",
                suppress_embeds=True,
            )
            return

        display = ""
        for i, (title, url, *_) in enumerate(self.queue[:10]):
            display += f"{i + 1}. [{title}]({url})\n"
        await send_message(
            interaction,
            f"{now_playing}🎶 현재 대기열:\n{display}",
            suppress_embeds=True,
        )

    @app_commands.command(name="remove", description="대기열에서 특정 곡을 제거합니다.")
    @app_commands.describe(index="제거할 곡 번호 (1부터 시작)")
    async def remove_command(self, interaction: discord.Interaction, index: int):
        if index < 1 or index > len(self.queue):
            await send_message(
                interaction, "❌ 유효하지 않은 번호입니다.", ephemeral=True
            )
            return
        vc = discord.utils.get(self.bot.voice_clients, guild=interaction.guild)
        if Music.has_permission(interaction, self.queue[index - 1], vc):
            title, url, *_ = self.queue.pop(index - 1)
            await send_message(
                interaction, f"🗑️ `[{title}]({url})`을 대기열에서 제거했어요."
            )
        else:
            await send_message(interaction, "❌ 해당 곡을 삭제할 권한이 없어요.")

    @app_commands.command(name="leave", description="봇을 음성 채널에서 나가게 합니다.")
    async def leave(self, interaction: discord.Interaction):
        await self.leave_channel(interaction.guild, interaction)

    def get_now_playing_text(self):
        if self.current:
            title, url, *_ = self.current
            return f"🎶 현재 재생 중: **[{title}]({url})**"
        else:
            return "❌ 현재 재생 중인 곡이 없습니다."

    @app_commands.command(
        name="nowplaying", description="현재 재생 중인 곡을 표시합니다."
    )
    async def nowplaying(self, interaction: discord.Interaction):
        text = self.get_now_playing_text()
        await send_message(interaction, text)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
