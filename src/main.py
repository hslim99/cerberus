import os
import discord
from discord.ext import commands
from log import init_log

from dotenv import load_dotenv
load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.dm_messages = True
intents.guilds = True
intents.bans = True
intents.guild_messages = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f'{bot.user}에 로그인하였습니다!')

init_log(bot)

bot.run(os.getenv("TOKEN"))
