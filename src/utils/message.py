import discord


async def send_message(
    interaction: discord.Interaction, content: str, *, followup=False, **kwargs
):
    content = "\n" + content.lstrip()
    if followup or interaction.response.is_done():
        await interaction.followup.send(content, **kwargs)
    else:
        await interaction.response.send_message(content, **kwargs)
