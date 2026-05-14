import discord
from discord import app_commands
import os
import json
import re
import secrets
import string
from datetime import datetime, timedelta

TOKEN = os.environ.get("TOKEN")
CHANNEL_ID = 1503261482907996170

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

ALLOWED_ROLES = {"Special", "Crown"}
KEYS_FILE = "keys.json"


def has_permission(interaction: discord.Interaction) -> bool:
    user_roles = {role.name for role in interaction.user.roles}
    return bool(user_roles & ALLOWED_ROLES)


def load_keys() -> dict:
    if not os.path.exists(KEYS_FILE):
        return {}
    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_keys(keys: dict):
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=4)


def generate_key(length: int = 24) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def parse_time(time_str: str):
    cleaned = time_str.strip().lower()
    if cleaned == "lt":
        return "lifetime"
    pattern = re.fullmatch(r"(\d+)(m|h|d)", cleaned)
    if not pattern:
        return None
    value, unit = int(pattern.group(1)), pattern.group(2)
    if unit == "m":
        return timedelta(minutes=value)
    elif unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)


def format_expiry(iso_str: str) -> str:
    if iso_str == "lifetime":
        return "Lifetime"
    expiry = datetime.fromisoformat(iso_str)
    now = datetime.utcnow()
    if expiry <= now:
        return "Expired"
    delta = expiry - now
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes = remainder // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "Less than a minute"


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
    deleted = await interaction.channel.purge(limit=amount, check=lambda m: m.webhook_id is None)
    await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)


@tree.command(name="newkey", description="Generate a new key for a user")
@app_commands.describe(time="Duration: 1m, 12h, 7d, lt (lifetime)", target="Target user")
async def newkey(interaction: discord.Interaction, time: str, target: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    delta = parse_time(time)
    if delta is None:
        await interaction.response.send_message(
            "Invalid time format. Use: `1m`, `12h`, `7d`, `lt`", ephemeral=True
        )
        return

    keys = load_keys()
    user_id = str(target.id)

    if user_id in keys:
        await interaction.response.send_message(
            f"{target.mention} already has a key. Use `/adjustkey` to change it or `/delkey` to remove it.",
            ephemeral=True
        )
        return

    key = generate_key()
    expiry = "lifetime" if delta == "lifetime" else (datetime.utcnow() + delta).isoformat()

    keys[user_id] = {
        "key": key,
        "expiry": expiry,
        "hwid": None,
        "username": str(target)
    }
    save_keys(keys)

    embed = discord.Embed(title="Key Generated", color=0x2ecc71)
    embed.add_field(name="User", value=target.mention, inline=True)
    embed.add_field(name="Expires in", value=format_expiry(expiry), inline=True)
    embed.add_field(name="Key", value=f"`{key}`", inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="delkey", description="Delete a user's key")
@app_commands.describe(target="Target user")
async def delkey(interaction: discord.Interaction, target: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    keys = load_keys()
    user_id = str(target.id)

    if user_id not in keys:
        await interaction.response.send_message(f"{target.mention} doesn't have a key.", ephemeral=True)
        return

    del keys[user_id]
    save_keys(keys)

    embed = discord.Embed(title="Key Deleted", color=0xe74c3c)
    embed.add_field(name="User", value=target.mention, inline=True)

    await interaction.response.send_message(embed=embed)


@tree.command(name="adjustkey", description="Adjust the duration of a user's key")
@app_commands.describe(target="Target user", time="New duration: 1m, 12h, 7d, lt (lifetime)")
async def adjustkey(interaction: discord.Interaction, target: discord.Member, time: str):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    delta = parse_time(time)
    if delta is None:
        await interaction.response.send_message(
            "Invalid time format. Use: `1m`, `12h`, `7d`, `lt`", ephemeral=True
        )
        return

    keys = load_keys()
    user_id = str(target.id)

    if user_id not in keys:
        await interaction.response.send_message(
            f"{target.mention} doesn't have a key. Use `/newkey` to create one.", ephemeral=True
        )
        return

    expiry = "lifetime" if delta == "lifetime" else (datetime.utcnow() + delta).isoformat()
    keys[user_id]["expiry"] = expiry
    save_keys(keys)

    embed = discord.Embed(title="Key Adjusted", color=0x3498db)
    embed.add_field(name="User", value=target.mention, inline=True)
    embed.add_field(name="New expiry", value=format_expiry(expiry), inline=True)
    embed.add_field(name="Key", value=f"`{keys[user_id]['key']}`", inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="keyinfo", description="Get info about a user's key")
@app_commands.describe(target="Target user")
async def keyinfo(interaction: discord.Interaction, target: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    keys = load_keys()
    user_id = str(target.id)

    if user_id not in keys:
        await interaction.response.send_message(f"{target.mention} doesn't have a key.", ephemeral=True)
        return

    data = keys[user_id]
    hwid_status = f"`{data['hwid']}`" if data.get("hwid") else "Not bound yet"

    embed = discord.Embed(title="Key Info", color=0x9b59b6)
    embed.add_field(name="User", value=target.mention, inline=True)
    embed.add_field(name="Time remaining", value=format_expiry(data["expiry"]), inline=True)
    embed.add_field(name="HWID", value=hwid_status, inline=False)
    embed.add_field(name="Key", value=f"`{data['key']}`", inline=False)

    await interaction.response.send_message(embed=embed)


@tree.command(name="resethwid", description="Reset HWID binding for a user")
@app_commands.describe(target="Target user")
async def resethwid(interaction: discord.Interaction, target: discord.Member):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    keys = load_keys()
    user_id = str(target.id)

    if user_id not in keys:
        await interaction.response.send_message(f"{target.mention} doesn't have a key.", ephemeral=True)
        return

    keys[user_id]["hwid"] = None
    save_keys(keys)

    embed = discord.Embed(title="HWID Reset", color=0xf39c12)
    embed.add_field(name="User", value=target.mention, inline=True)
    embed.description = "HWID has been unbound. Next login will bind a new HWID."

    await interaction.response.send_message(embed=embed)


@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot started: {client.user}")

client.run(TOKEN)
