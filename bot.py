import discord
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
        await interaction.followup.send("Channel not found!")
        return
    
    users = []
    message_count = 0
    
    async for message in channel.history(limit=500):
        message_count += 1
        for embed in message.embeds:
            print(f"Embed title: {repr(embed.title)}")
            for field in embed.fields:
                print(f"Field: {repr(field.name)} = {repr(field.value)}")
                if field.name == "Name":
                    value = field.value.replace("`", "").strip()
                    if value not in users:
                        users.append(value)
    
    if users:
        with open("reshape_users_dump.txt", "w") as f:
            f.write(" - ".join(users))
        await interaction.followup.send(f"Found {len(users)} users:", file=discord.File("reshape_users_dump.txt"))
    else:
        await interaction.followup.send(f"Checked {message_count} messages, no users found")

@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot started: {client.user}")

client.run(TOKEN)
