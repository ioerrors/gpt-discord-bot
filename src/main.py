# ───────────────────────────────────────────────────────────────
#  src/main.py   —  SkippyAI (no‑moderation edition)
# ───────────────────────────────────────────────────────────────
from collections import defaultdict
from typing import Optional, Literal

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
thread_data = defaultdict()


@client.event
async def on_ready():
    logger.info(f"We have logged in as {client.user}. Invite URL: {BOT_INVITE_URL}")
    # propagate bot name to completion module
    from src import completion

    completion.MY_BOT_NAME = client.user.name
    completion.MY_BOT_EXAMPLE_CONVOS = []
    for c in EXAMPLE_CONVOS:
        msgs = []
        for m in c.messages:
            user = client.user.name if m.user == "Lenard" else m.user
            msgs.append(Message(user=user, text=m.text))
        completion.MY_BOT_EXAMPLE_CONVOS.append(Conversation(messages=msgs))

    await tree.sync()


# ───────────────────────────────────────────────────────────────
# /chat  slash‑command
# ───────────────────────────────────────────────────────────────
@tree.command(name="chat", description="Create a new thread for conversation")
@discord.app_commands.checks.has_permissions(send_messages=True, view_channel=True)
@discord.app_commands.checks.bot_has_permissions(
    send_messages=True, view_channel=True, manage_threads=True
)
@app_commands.describe(message="The first prompt to start the chat with")
@app_commands.describe(model="The model to use for the chat")
@app_commands.describe(
    temperature="Controls randomness (0‑1). Higher = more creative."
)
@app_commands.describe(
    max_tokens="Max tokens the model may generate per reply (1‑4096)."
)
async def chat_command(  # noqa: N802  (discord uses "int" param name)
    int: discord.Interaction,
    message: str,
    model: AVAILABLE_MODELS = DEFAULT_MODEL,
    temperature: Optional[float] = 1.0,
    max_tokens: Optional[int] = 512,
):
    try:
        # Only allow invocations from text channels
        if not isinstance(int.channel, discord.TextChannel):
            return

        # Block guilds not in allow‑list
        if should_block(guild=int.guild):
            return

        # Validate numeric params
        if not 0 <= temperature <= 1:
            await int.response.send_message(
                f"Invalid temperature {temperature} (0‑1 required)", ephemeral=True
            )
            return
        if not 1 <= max_tokens <= 4096:
            await int.response.send_message(
                f"Invalid max_tokens {max_tokens} (1‑4096 required)", ephemeral=True
            )
            return

        user = int.user
        logger.info(f"/chat by {user} – {message[:50]}")

        # Build & send an embed summarizing the request
        embed = discord.Embed(
            description=f"<@{user.id}> wants to chat! 🤖💬",
            color=discord.Color.green(),
        )
        embed.add_field(name="model", value=model)
        embed.add_field(name="temperature", value=temperature, inline=True)
        embed.add_field(name="max_tokens", value=max_tokens, inline=True)
        embed.add_field(name=user.name, value=message)

        await int.response.send_message(embed=embed)
        response_msg = await int.original_response()

        # Create a thread for the conversation
        thread = await response_msg.create_thread(
            name=f"{ACTIVATE_THREAD_PREFX} {user.name[:20]} - {message[:30]}",
            reason="SkippyAI chat",
            slowmode_delay=0,
            auto_archive_duration=60,
        )
        thread_data[thread.id] = ThreadConfig(model, max_tokens, temperature)

        # Generate first reply
        async with thread.typing():
            messages = [Message(user=user.name, text=message)]
            data = await generate_completion_response(messages, thread_data[thread.id])
            await process_response(thread, data)

    except Exception as exc:  # noqa: BLE001
        logger.exception(exc)
        await int.response.send_message(f"Error starting chat: {exc}", ephemeral=True)


# ───────────────────────────────────────────────────────────────
# Handle every message inside a thread the bot owns
# ───────────────────────────────────────────────────────────────
@client.event
async def on_message(msg: DiscordMessage):
    try:
        if msg.author == client.user:
            return
        if not isinstance(msg.channel, discord.Thread):
            return

        thread = msg.channel
        if thread.owner_id != client.user.id:
            return
        if thread.archived or thread.locked or not thread.name.startswith(
            ACTIVATE_THREAD_PREFX
        ):
            return
        if thread.message_count > MAX_THREAD_MESSAGES:
            await close_thread(thread)
            return
        if should_block(guild=msg.guild):
            return

        # Optional batching delay
        if SECONDS_DELAY_RECEIVING_MSG:
            await asyncio.sleep(SECONDS_DELAY_RECEIVING_MSG)
            if is_last_message_stale(msg, thread.last_message, client.user.id):
                return

        logger.info(
            f"Processing thread msg – {msg.author}: {msg.content[:60]} ({thread.jump_url})"
        )

        # Reconstruct conversation context
        history = [
            discord_message_to_message(m)
            async for m in thread.history(limit=MAX_THREAD_MESSAGES)
        ]
        history = [h for h in history if h]
        history.reverse()

        async with thread.typing():
            data = await generate_completion_response(history, thread_data[thread.id])

        if is_last_message_stale(msg, thread.last_message, client.user.id):
            return

        await process_response(thread, data)

    except Exception as exc:  # noqa: BLE001
        logger.exception(exc)


# ───────────────────────────────────────────────────────────────
client.run(DISCORD_BOT_TOKEN)
