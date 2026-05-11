import discord
from discord.ext import commands
from discord import app_commands

TOKEN = "MTUwMzI2Mjg1MzM0NjYyNzY2Ng.GR3FTR.G0dsI2HOGtCRkgfoaLQlAHOlMm877atu3gVKJY"
CHANNEL_ID = 1503261482907996170

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@tree.command(name="dump_reshape_users", description="Dumps reshape users, updates their info to keep undetected.")
async def dump_users(interaction: discord.Interaction):
    channel = client.get_channel(CHANNEL_ID)
    users = []

    async for message in channel.history(limit=500):
        if message.embeds:
            for embed in message.embeds:
                if embed.title == "Execute Log" and embed.description:
                    for line in embed.description.split("\n"):
                        if "**Player:**" in line:
                            name = line.replace("**Player:**", "").strip()
                            if name not in users:
                                users.append(name)

    if not users:
        await interaction.response.send_message("Logs not found.")
        return

    with open("users.txt", "w") as f:
        f.write("\n".join(users))

    await interaction.response.send_message(file=discord.File("users.txt"))

@client.event
async def on_ready():
    await tree.sync()
    print(f"Бот запущен: {client.user}")

client.run(TOKEN)
