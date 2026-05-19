import discord
from discord import app_commands
import os
import json
import re
import secrets
import string
import asyncio
import websockets
from datetime import datetime, timedelta

TOKEN = os.environ.get("TOKEN")
CHANNEL_ID = 1503261482907996170
WS_PORT = int(os.environ.get("PORT", 8080))

intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

ALLOWED_ROLES = {"Special", "Crown"}
KEYS_FILE = "keys.json"


# ── Утилиты ───────────────────────────────────────────────────────────────────

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
    if cleaned in ("lt", "lifetime"):
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


def check_key(key: str, hwid: str) -> dict:
    keys = load_keys()

    for user_id, data in keys.items():
        if data["key"] != key:
            continue

        if data["expiry"] != "lifetime":
            expiry = datetime.fromisoformat(data["expiry"])
            if datetime.utcnow() > expiry:
                return {"status": "expired"}

        if not data.get("hwid"):
            data["hwid"] = hwid
            save_keys(keys)
            return {"status": "ok", "user": data["username"]}

        if data["hwid"] == hwid:
            return {"status": "ok", "user": data["username"]}
        else:
            return {"status": "hwid_mismatch"}

    return {"status": "invalid"}


# ── WebSocket сервер ──────────────────────────────────────────────────────────

async def ws_handler(websocket):
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                key = data.get("key", "").strip()
                hwid = data.get("hwid", "").strip()

                if not key or not hwid:
                    await websocket.send(json.dumps({"status": "invalid"}))
                    continue

                result = check_key(key, hwid)
                await websocket.send(json.dumps(result))

            except json.JSONDecodeError:
                await websocket.send(json.dumps({"status": "invalid"}))
    except websockets.exceptions.ConnectionClosed:
        pass


async def start_ws():
    print(f"WebSocket server started on port {WS_PORT}")
    async with websockets.serve(ws_handler, "0.0.0.0", WS_PORT):
        await asyncio.Future()


# ── Discord команды ───────────────────────────────────────────────────────────

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


@tree.command(name="gen", description="Generate multiple unbound keys")
@app_commands.describe(
    amount="How many keys to generate (1–100)",
    time="Duration: 1m, 12h, 7d, lifetime"
)
async def gen(interaction: discord.Interaction, amount: int, time: str):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    if amount < 1 or amount > 100:
        await interaction.response.send_message("Amount must be between 1 and 100.", ephemeral=True)
        return

    delta = parse_time(time)
    if delta is None:
        await interaction.response.send_message(
            "Invalid time format. Use: `1m`, `12h`, `7d`, `lifetime`", ephemeral=True
        )
        return

    expiry = "lifetime" if delta == "lifetime" else (datetime.utcnow() + delta).isoformat()

    keys = load_keys()
    generated = []

    for _ in range(amount):
        key = generate_key()
        # Уникальный internal ID для висячих ключей
        internal_id = f"unbound_{secrets.token_hex(8)}"
        keys[internal_id] = {
            "key": key,
            "expiry": expiry,
            "hwid": None,
            "username": "Unbound"
        }
        generated.append(key)

    save_keys(keys)

    # Формируем .txt файл
    expiry_label = format_expiry(expiry)
    txt_content = "\n".join(generated)
    filename = f"keys_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(txt_content)

    embed = discord.Embed(title="Keys Generated", color=0x2ecc71)
    embed.add_field(name="Amount", value=str(amount), inline=True)
    embed.add_field(name="Duration", value=expiry_label, inline=True)
    embed.add_field(name="Generated by", value=interaction.user.mention, inline=True)

    await interaction.response.send_message(embed=embed, file=discord.File(filename))
    os.remove(filename)


@tree.command(name="connect", description="Link your license key to your Discord account")
@app_commands.describe(accountkey="Your license key")
async def connect(interaction: discord.Interaction, accountkey: str):
    keys = load_keys()
    accountkey = accountkey.strip()

    found_id = None
    found_data = None
    for user_id, data in keys.items():
        if data["key"] == accountkey:
            found_id = user_id
            found_data = data
            break

    if not found_data:
        await interaction.response.send_message("Invalid key.", ephemeral=True)
        return

    if found_data["expiry"] != "lifetime":
        expiry_dt = datetime.fromisoformat(found_data["expiry"])
        if datetime.utcnow() > expiry_dt:
            await interaction.response.send_message("This key has expired.", ephemeral=True)
            return

    user_id_str = str(interaction.user.id)

    # Если ключ уже привязан к другому Discord аккаунту
    if not found_id.startswith("unbound_") and found_id != user_id_str:
        await interaction.response.send_message("This key is already linked to another account.", ephemeral=True)
        return

    # Если у пользователя уже есть другой ключ
    if user_id_str in keys and keys[user_id_str]["key"] != accountkey:
        await interaction.response.send_message(
            "❌ You already have a different key linked.",
            ephemeral=True
        )
        return

    # Переносим unbound ключ на Discord ID пользователя
    if found_id.startswith("unbound_"):
        found_data["username"] = str(interaction.user)
        keys[user_id_str] = found_data
        del keys[found_id]
        save_keys(keys)

    await interaction.response.send_message("Key successfully linked to your account!", ephemeral=True)


@tree.command(name="info", description="Check your license status")
async def info(interaction: discord.Interaction):
    keys = load_keys()
    user_id_str = str(interaction.user.id)

    if user_id_str not in keys:
        await interaction.response.send_message(
            "No key linked. Use `/connect` to link your key.", ephemeral=True
        )
        return

    data = keys[user_id_str]

    if data["expiry"] == "lifetime":
        time_text = "Lifetime"
    else:
        expiry_dt = datetime.fromisoformat(data["expiry"])
        now = datetime.utcnow()
        if expiry_dt <= now:
            time_text = "Expired"
        else:
            delta = expiry_dt - now
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes = remainder // 60

            if days > 0:
                time_text = f"{days} days remaining!"
            elif hours > 0:
                time_text = f"{hours} hours remaining!"
            else:
                time_text = f"{minutes} minutes remaining!"

    await interaction.response.send_message(time_text, ephemeral=True)


admin_group = app_commands.Group(name="admin", description="Admin commands")
tree.add_command(admin_group)


@admin_group.command(name="checklicense", description="Check info about a key")
@app_commands.describe(license="The license key to check")
async def checklicense(interaction: discord.Interaction, license: str):
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return

    keys = load_keys()
    license = license.strip()

    found_id = None
    found_data = None
    for user_id, data in keys.items():
        if data["key"] == license:
            found_id = user_id
            found_data = data
            break

    if not found_data:
        await interaction.response.send_message(
            f"❌ Key `{license}` not found.", ephemeral=True
        )
        return

    is_unbound = found_id.startswith("unbound_")
    hwid_status = f"`{found_data['hwid']}`" if found_data.get("hwid") else "Not bound yet"
    expiry_label = format_expiry(found_data["expiry"])

    if found_data["expiry"] != "lifetime":
        expiry_dt = datetime.fromisoformat(found_data["expiry"])
        is_expired = datetime.utcnow() > expiry_dt
    else:
        is_expired = False

    embed = discord.Embed(
        title="License Info",
        color=0xe74c3c if is_expired else 0x9b59b6
    )
    embed.add_field(name="Key", value=f"`{license}`", inline=False)
    embed.add_field(
        name="Owner",
        value="Unbound (no Discord user)" if is_unbound else f"<@{found_id}> (`{found_data['username']}`)",
        inline=True
    )
    embed.add_field(
        name="Status",
        value="Expired" if is_expired else "Active",
        inline=True
    )
    embed.add_field(name="Time remaining", value=expiry_label, inline=True)
    embed.add_field(name="HWID", value=hwid_status, inline=False)

    await interaction.response.send_message(embed=embed)


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
    embed.description = "HWID has been unbound. Next login will bind a new HWID."
    embed.add_field(name="User", value=target.mention, inline=True)

    await interaction.response.send_message(embed=embed)


# ── Запуск ────────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    await tree.sync()
    print(f"Bot started: {client.user}")


async def main():
    await asyncio.gather(
        start_ws(),
        client.start(TOKEN)
    )


asyncio.run(main())
