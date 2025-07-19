# ───────────────────────────────────────────────────────────────
#  src/main.py  —  SkippyAI (no‑moderation, restart‑safe)
# ───────────────────────────────────────────────────────────────
from collections import defaultdict
from typing import Optional

import asyncio
import logging
import discord
from discord import Message as DiscordMessage, app_commands

from src.base import Message, Conversation, ThreadConfig
from src.constants import (
    BOT_INVITE_URL,
    DISCORD_BOT_TOKEN,
    EXAMPLE_CONVOS,
    ACTIVATE_THREAD_PREFX,
    MAX_THREAD_MESSAGES,
    SECONDS_DELAY_RECEIVING_MSG,
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
)
from src.utils import (
    logger,
    should_block,
    close_thread,
    is_last_message_stale,
    discord_message_to_message,
)
from src.completion import generate_completion_response, process_response

logging.basicConfig(
    format="[%(asctime)s] [%(filename)s:%(lineno)d] %(message)s",
    level=logging.INFO,
)

# ───────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = discord.app_commands.CommandTree(client)
thread_data: dict[int, ThreadConfig] = defaultdict()

# ───────────────────────────────────────────────────────────────
@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user}. Invite URL: {BOT_INVITE_URL}")

    # propagate bot name & example convos to completion module
    from src import completion

    completion.MY_BOT_NAME = client.user.name
    completion.MY_BOT_EXAMPLE_CONVOS = []
    for convo in EXAMPLE_CONVOS:
        msgs = [
            Message(user=(client.user.name if m.user == "Lenard" else m.user), text=m.text)
            for m in convo.messages
        ]
        completion.MY_BOT_EXAMPLE_CONVOS.append(Conversation(messages=msgs))

    await tree.sync()

# ───────────────────────────────────────────────────────────────
# /chat  slash command
# ───────────────────────────────────────────────────────────────
@tree.command(name="chat", description="Start a new SkippyAI thread")
@discord.app_commands.checks.bot_has_permissions(
    send_messages=True, view_channel=True, manage_threads=True
)
@app_commands.describe(
    temperature="Randomness (0‑1). Higher = more creative.",
    max_tokens="Max tokens SkippyAI may generate in one reply (1‑4096).",
)
async def chat_command(  # noqa: N802 (discord uses "int" param name)
    int: discord.Interaction,
    message: str,
    model: AVAILABLE_MODELS = "gpt-4o-mini",  # literal so Discord validates
    temperature: Optional[float] = 1.0,
    max_tokens: Optional[int] = 512,
):
    try:
        if not isinstance(int.channel, discord.TextChannel):
            return
        if should_block(int.guild):
            return
        if not 0 <= temperature <= 1 or not 1 <= max_tokens <= 4096:
            await int.response.send_message(
                "Invalid temperature or max_tokens range.", ephemeral=True
            )
            return

        user = int.user
        logger.info(f"/chat by {user} – {message[:60]}")

        # 1️⃣  Defer immediately so Discord gets an ACK
        await int.response.defer()

        # Build a pretty embed summarising the request
        embed = (
            discord.Embed(
                description=f"<@{user.id}> wants to chat! 🤖💬",
                color=discord.Color.green(),
            )
            .add_field(name="model", value=model)
            .add_field(name="temperature", value=temperature, inline=True)
            .add_field(name="max_tokens", value=max_tokens, inline=True)
            .add_field(name=user.name, value=message)
        )

        # 2️⃣  Send follow‑up message (becomes thread starter)
        response_msg = await int.followup.send(embed=embed)

        # Create the thread
        thread = await response_msg.create_thread(
            name=f"{ACTIVATE_THREAD_PREFX} {user.name[:20]} - {message[:30]}",
            reason="SkippyAI chat",
            slowmode_delay=0,
            auto_archive_duration=60,
        )
        thread_data[thread.id] = ThreadConfig(model, max_tokens, temperature)

        # Generate first reply
        async with thread.typing():
            data = await generate_completion_response(
                [Message(user=user.name, text=message)],
                thread_data[thread.id],
            )
            await process_response(thread, data)

    except Exception as exc:  # noqa: BLE001
        logger.exception(exc)
        if not int.response.is_done():
            await int.response.send_message(f"Error: {exc}", ephemeral=True)

# ───────────────────────────────────────────────────────────────
# Handle every message inside a thread the bot owns
# ───────────────────────────────────────────────────────────────
@client.event
async def on_message(msg: DiscordMessage):
    try:
        if msg.author == client.user or not isinstance(msg.channel, discord.Thread):
            return

        thread: discord.Thread = msg.channel
        if (
            thread.owner_id != client.user.id
            or thread.archived
            or thread.locked
            or not thread.name.startswith(ACTIVATE_THREAD_PREFX)
        ):
            return
        if should_block(msg.guild):
            return
        if thread.message_count > MAX_THREAD_MESSAGES:
            await close_thread(thread)
            return

        # Ensure config exists for threads across restarts
        if thread.id not in thread_data:
            thread_data[thread.id] = ThreadConfig(
                model=DEFAULT_MODEL, max_tokens=512, temperature=1.0
            )

        # Optional batching
        if SECONDS_DELAY_RECEIVING_MSG:
            await asyncio.sleep(SECONDS_DELAY_RECEIVING_MSG)
            if is_last_message_stale(msg, thread.last_message, client.user.id):
                return

        logger.info(
            f"Thread msg – {msg.author}: {msg.content[:60]} ({thread.jump_url})"
        )

        # Build conversation context
        history = [
            m
            async for m in thread.history(limit=MAX_THREAD_MESSAGES)
        ]
        history = [discord_message_to_message(m) for m in history if m]
        history.reverse()

        async with thread.typing():
            data = await generate_completion_response(
                history, thread_data[thread.id]
            )
        if is_last_message_stale(msg, thread.last_message, client.user.id):
            return
        await process_response(thread, data)

    except Exception as exc:  # noqa: BLE001
        logger.exception(exc)

# ───────────────────────────────────────────────────────────────
client.run(DISCORD_BOT_TOKEN)
