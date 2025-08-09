from src.constants import (
    ALLOWED_SERVER_IDS,
)
import logging

logger = logging.getLogger(__name__)
from src.base import Message
from discord import Message as DiscordMessage
from typing import Optional, List
import discord

from src.constants import MAX_CHARS_PER_REPLY_MSG, INACTIVATE_THREAD_PREFIX


def discord_message_to_message(message: DiscordMessage) -> Optional[Message]:
    if (
        message.type == discord.MessageType.thread_starter_message
        and message.reference
        and message.reference.cached_message
        and message.reference.cached_message.embeds
        and message.reference.cached_message.embeds[0].fields
    ):
        fields = message.reference.cached_message.embeds[0].fields
        META = {"model", "temperature", "max_tokens"}
        # Prefer the field that looks like the user prompt
        for f in fields:
            if f.name and f.value and f.name.lower() not in META:
                return Message(user=f.name, text=f.value)
        # Fallback: first field if nothing matched
        f0 = fields[0]
        if f0.value:
            return Message(user=f0.name, text=f0.value)

    else:
        if message.content:
            return Message(user=message.author.name, text=message.content)

    return None



def split_into_shorter_messages(message: str) -> List[str]:
    return [
        message[i : i + MAX_CHARS_PER_REPLY_MSG]
        for i in range(0, len(message), MAX_CHARS_PER_REPLY_MSG)
    ]


def is_last_message_stale(
    interaction_message: DiscordMessage, last_message: DiscordMessage, bot_id: str
) -> bool:
    return (
        last_message
        and last_message.id != interaction_message.id
        and last_message.author
        and last_message.author.id != bot_id
    )


async def close_thread(thread: discord.Thread):
    # Preserve existing title while swapping active→inactive prefix
    from src.constants import ACTIVATE_THREAD_PREFX, INACTIVATE_THREAD_PREFIX
    try:
        current = thread.name or ""
        title = current
        if current.startswith(ACTIVATE_THREAD_PREFX):
            title = current[len(ACTIVATE_THREAD_PREFX):].lstrip()
        elif current.startswith(INACTIVATE_THREAD_PREFIX):
            title = current[len(INACTIVATE_THREAD_PREFIX):].lstrip()
        new_name = f"{INACTIVATE_THREAD_PREFIX} {title}" if title else INACTIVATE_THREAD_PREFIX
        await thread.edit(name=new_name)
    except Exception:
        # Fallback to prefix only
        await thread.edit(name=INACTIVATE_THREAD_PREFIX)
    await thread.send(
        embed=discord.Embed(
            description="**Thread closed** - Context limit reached, closing...",
            color=discord.Color.blue(),
        )
    )
    await thread.edit(archived=True, locked=True)


def should_block(guild: Optional[discord.Guild]) -> bool:
    if guild is None:
        # dm's not supported
        logger.info(f"DM not supported")
        return True

    if guild.id and guild.id not in ALLOWED_SERVER_IDS:
        # not allowed in this server
        logger.info(f"Guild {guild} not allowed")
        return True
    return False
