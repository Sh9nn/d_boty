import discord
from discord.ext import commands
from discord import app_commands
import os

TOKEN = os.environ.get("TOKEN")
CHANNEL_ID = 1503261482907996170

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@tree.command(name="dump_reshape_users", description="Dumps reshape users, updates their info to stay undetected")
async def dump_users(interaction: discord.Interaction):
    await interaction.response.defer()
    
    channel = client.get_channel(CHANNEL_ID)
    
    if not channel:
        await interaction.followup.send("Channel not found")
        return
    
    users = []
    message_count = 0
    
    async for message in channel.history(limit=500):
        message_count += 1
        if message.embeds:
            for embed in message.embeds:
                if embed.description:
                    for line in embed.description.split("\n"):
                        if "**Player:**" in line:
                            name = line.replace("**Player:**", "").strip()
                            if name not in users:
                                users.append(name)
    
    if users:
        await interaction.followup.send(f"Проверено сообщений: {message_count}, найдено юзеров: {len(users)}\n" + "\n".join(users))
    else:
        await interaction.followup.send(f"Проверено сообщений: {message_count}, юзеров не найдено")

@client.event
async def on_ready():
    await tree.sync()
    print(f"Бот запущен: {client.user}")

client.run(TOKEN)
