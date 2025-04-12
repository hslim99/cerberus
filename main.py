import os
import sys
import traceback

import discord
from discord.ext import commands
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.dm_messages = True
intents.guilds = True
intents.bans = True
intents.guild_messages = True
intents.voice_states = True
intents.message_content = True


class Cerberus(commands.Bot):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=int(os.getenv("GUILD_ID")))

        await self.load_extension("cogs.music")
        await self.load_extension("cogs.logger")

        await self.tree.sync(guild=guild)
        print("✅ Slash 명령어 동기화 완료!")


bot = Cerberus(intents=intents)


@bot.event
async def on_ready():
    print(f"{bot.user}에 로그인하였습니다!")


if __name__ == "__main__":
    try:
        bot.run(os.getenv("TOKEN"))
    except Exception as e:
        print("치명적인 오류 발생. 봇을 종료합니다.")
        traceback.print_exc()
        sys.exit(1)