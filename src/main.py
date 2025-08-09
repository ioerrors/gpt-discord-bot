# ───────────────────────────────────────────────────────────────
#  src/main.py  —  SkippyAI (restart‑safe, no‑moderation)
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
from src.completion import generate_completion_response, process_response, generate_title

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

    # propagate bot name & examples to completion.py
    from src import completion
    completion.MY_BOT_NAME = client.user.name
    completion.MY_BOT_EXAMPLE_CONVOS = [
        Conversation(
            messages=[
                Message(
                    user=(client.user.name if m.user == "Lenard" else m.user),
                    text=m.text,
                )
                for m in convo.messages
            ]
        )
        for convo in EXAMPLE_CONVOS
    ]

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
async def chat_command(  # noqa: N802
    int: discord.Interaction,
    message: str,
    model: AVAILABLE_MODELS = "gpt-5",   # literal default
    temperature: Optional[float] = 1.0,
    max_tokens: Optional[int] = 512,
):
    try:
        # Preconditions -------------------------------------------------------
        if not isinstance(int.channel, discord.TextChannel):
            return
        if should_block(int.guild):
            return
        if not 0 <= temperature <= 1 or not 1 <= max_tokens <= 4096:
            await int.response.send_message(
                "Invalid temperature or max_tokens.", ephemeral=True
            )
            return

        user = int.user
        logger.info(f"/chat by {user} – {message[:60]}")

        # Send an immediate embed (Discord 3s rule)
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
        await int.response.send_message(embed=embed)
        response_msg = await int.original_response()

        # Generate a catchy thread title with GPT‑mini
        title = await generate_title(message)  

        # Create the thread
        thread = await response_msg.create_thread(
            name=f"{ACTIVATE_THREAD_PREFX} {title}",
            slowmode_delay=0,
            auto_archive_duration=60,
            reason="SkippyAI chat",
        )
        thread_data[thread.id] = ThreadConfig(model, max_tokens, temperature)

        # First reply from Skippy
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
# Handle messages in bot‑owned threads
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

        # Re‑attach default config if bot restarted
        if thread.id not in thread_data:
            thread_data[thread.id] = ThreadConfig(
                model=DEFAULT_MODEL, max_tokens=512, temperature=1.0
            )

        # Optional batching delay
        if SECONDS_DELAY_RECEIVING_MSG:
            await asyncio.sleep(SECONDS_DELAY_RECEIVING_MSG)
            if is_last_message_stale(msg, thread.last_message, client.user.id):
                return

        logger.info(
            f"Thread msg – {msg.author}: {msg.content[:60]} ({thread.jump_url})"
        )

        history = [
            discord_message_to_message(m)
            async for m in thread.history(limit=MAX_THREAD_MESSAGES)
        ]
        history = [m for m in history if m]
        history.reverse()

        async with thread.typing():
            data = await generate_completion_response(
                history, thread_data[thread.id]
            )
        if is_last_message_stale(msg, thread.last_message, client.user.id):
            return
        await process_response(thread, data)

    except Exception as exc:
        logger.exception(exc)



# ───────────────────────────────────────────────────────────────
# /research command (placeholder; disabled by default)
# ───────────────────────────────────────────────────────────────
@tree.command(name="research", description="Research with citations (placeholder; disabled by default)")
@discord.app_commands.checks.bot_has_permissions(
    send_messages=True, view_channel=True, manage_threads=True
)
@app_commands.describe(
    query="What do you want me to research?",
    depth="How deep to go (1-3)"
)
async def research_command(int: discord.Interaction, query: str, depth: Optional[int] = 1):  # noqa: N802
    from src.constants import RESEARCH_ENABLED
    if not isinstance(int.channel, discord.TextChannel):
        return
    if should_block(int.guild):
        return
    if not RESEARCH_ENABLED:
        await int.response.send_message(
            "Research mode is disabled in this build. Set `RESEARCH_ENABLED=true` to enable (tools will be wired in a later patch).",
            ephemeral=True
        )
        return
    await int.response.send_message("Research mode scaffold enabled, but tools not wired yet. Coming soon.", ephemeral=True)
# ───────────────────────────────────────────────────────────────
client.run(DISCORD_BOT_TOKEN)
