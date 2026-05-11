import discord
from discord import app_commands
import os

TOKEN = os.environ.get("TOKEN")
CHANNEL_ID = 1503261482907996170

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

ALLOWED_ROLES = {"Special", "Crown"}

def has_permission(interaction: discord.Interaction) -> bool:
    user_roles = {role.name for role in interaction.user.roles}
    return bool(user_roles & ALLOWED_ROLES)

@tree.command(name="dump_reshape_users", description="Dumps reshape users, updates their info to stay undetected")
async def dump_users(interaction: discord.Interaction):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

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
            name_value = None
            executor_value = None
            for field in embed.fields:
                if field.name == "Name":
                    name_value = field.value.replace("`", "").strip()
                if field.name == "User executor":
                    executor_value = field.value.replace("`", "").strip()
            if name_value:
                entry = f"{name_value} [Executed on: {executor_value or 'Unknown'}]"
                if entry not in users:
                    users.append(entry)
    
    if users:
        with open("reshape_users_dump.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(users))
        await interaction.followup.send(f"Found {len(users)} users:", file=discord.File("reshape_users_dump.txt"))
    else:
        await interaction.followup.send(f"Checked {message_count} messages, no users found")

@tree.command(name="clear", description="Clear messages in the channel")
@app_commands.describe(amount="Number of messages to delete")
async def clear(interaction: discord.Interaction, amount: int):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    if amount < 1 or amount > 100:
        await interaction.response.send_message("Amount must be between 1 and 100.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot started: {client.user}")

client.run(TOKEN)
