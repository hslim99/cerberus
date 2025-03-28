import os

import discord
import requests
from discord.ext import commands

IMAGE_DIRECTORY = "./images"
VALID_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif"]
MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25MB


class Logger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        log_channel = self.bot.get_channel(int(os.getenv("LOG_CHANNEL")))
        if not log_channel:
            print("Logging failed due to an invalid logChannel!")
            return

        if message.channel.id == int(os.getenv("TARGET_CHANNEL")):
            image_paths = []
            for attachment in message.attachments:
                file_extension = os.path.splitext(attachment.filename)[1].lower()
                file_name = f"{message.id}{attachment.id}{file_extension}"
                image_path = os.path.join(IMAGE_DIRECTORY, file_name)
                image_paths.append(image_path)

            if image_paths:
                await log_channel.send(
                    content=f"{message.author.name} (userId: {message.author.id}): {message.content}",
                    files=[discord.File(image_path) for image_path in image_paths],
                )
            else:
                await log_channel.send(
                    content=f"{message.author.name} (userId: {message.author.id}): {message.content}"
                )
        print(message)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        log_channel = self.bot.get_channel(int(os.getenv("LOG_CHANNEL")))
        if not log_channel:
            print("Logging failed due to an invalid logChannel!")
            return

        if message.channel.id == int(os.getenv("TARGET_CHANNEL")):
            for attachment in message.attachments:
                file_extension = os.path.splitext(attachment.filename)[1].lower()
                if file_extension not in VALID_EXTENSIONS:
                    continue
                if attachment.size > MAX_SIZE_BYTES:
                    continue
                if not os.path.exists(IMAGE_DIRECTORY):
                    os.makedirs(IMAGE_DIRECTORY)

                file_name = f"{message.id}{attachment.id}{file_extension}"
                file_path = os.path.join(IMAGE_DIRECTORY, file_name)

                try:
                    response = requests.get(attachment.url, stream=True)
                    if response.status_code == 200:
                        with open(file_path, "wb") as f:
                            for chunk in response.iter_content(chunk_size=1024):
                                if chunk:
                                    f.write(chunk)
                        print(f"Image uploaded and saved as: {file_name}")
                    else:
                        print(f"Failed to download image from {attachment.url}")
                except Exception as e:
                    print(f"Error saving image: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Logger(bot))
