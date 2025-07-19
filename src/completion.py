# completion.py  –  SkippyAI edition: no moderation, 1900‑char chunks, /continue
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict

import openai
from openai import AsyncOpenAI
import discord

from src.constants import BOT_INSTRUCTIONS, BOT_NAME, EXAMPLE_CONVOS, MAX_CHARS_PER_REPLY_MSG
from src.base import Message, Prompt, Conversation, ThreadConfig
from src.utils import split_into_shorter_messages, close_thread, logger

MY_BOT_NAME = BOT_NAME
MY_BOT_EXAMPLE_CONVOS = EXAMPLE_CONVOS

# ───────────────────────────────────────────────────────────────
class CompletionResult(Enum):
    OK = 0
    TOO_LONG = 1
    INVALID_REQUEST = 2
    OTHER_ERROR = 3


@dataclass
class CompletionData:
    status: CompletionResult
    reply_text: Optional[str]
    status_text: Optional[str]


client = AsyncOpenAI()

# ───────────────────────────────────────────────────────────────
# Internal store for "continue" payloads keyed by (guild_id, thread_id)
PENDING_REPLIES: Dict[tuple[int, int], List[str]] = {}
CONTINUE_HINT = "\n\n*(type `continue` for more)*"

# ───────────────────────────────────────────────────────────────
async def generate_completion_response(
    messages: List[Message],
    thread_config: ThreadConfig,
) -> CompletionData:
    prompt = Prompt(
        header=Message("system", f"Instructions for {MY_BOT_NAME}: {BOT_INSTRUCTIONS}"),
        examples=MY_BOT_EXAMPLE_CONVOS,
        convo=Conversation(messages),
    )
    rendered = prompt.full_render(MY_BOT_NAME)

    try:
        response = await client.chat.completions.create(
            model=thread_config.model,
            messages=rendered,
            temperature=thread_config.temperature,
            top_p=1.0,
            max_tokens=thread_config.max_tokens,
            stop=["<|endoftext|>"],
        )
        reply = response.choices[0].message.content.strip()
        return CompletionData(CompletionResult.OK, reply, None)

    except openai.BadRequestError as e:
        if "maximum context length" in str(e):
            return CompletionData(CompletionResult.TOO_LONG, None, str(e))
        return CompletionData(CompletionResult.INVALID_REQUEST, None, str(e))

    except Exception as e:
        logger.exception(e)
        return CompletionData(CompletionResult.OTHER_ERROR, None, str(e))

# ───────────────────────────────────────────────────────────────
async def process_response(
    thread: discord.Thread,
    response_data: CompletionData,
):
    status, reply_text, status_text = (
        response_data.status,
        response_data.reply_text,
        response_data.status_text,
    )

    if status is CompletionResult.OK:
        if not reply_text:
            await thread.send(
                embed=discord.Embed(
                    description="**Invalid response** – empty text",
                    color=discord.Color.yellow(),
                )
            )
            return

        chunks = split_into_shorter_messages(reply_text)   # drop 2nd arg
        if len(chunks) > 1:
            # Keep the extra chunks aside and hint user
            key = (thread.guild.id, thread.id)
            PENDING_REPLIES[key] = chunks[1:]
            chunks[-1] += CONTINUE_HINT

        for chunk in chunks[:1]:  # send only the first chunk now
            await thread.send(chunk)

    elif status is CompletionResult.TOO_LONG:
        await close_thread(thread)

    else:  # INVALID_REQUEST or OTHER_ERROR
        await thread.send(
            embed=discord.Embed(
                description=f"**Error** – {status_text}",
                color=discord.Color.red(),
            )
        )

# ───────────────────────────────────────────────────────────────
async def maybe_continue(thread: discord.Thread):
    """If the user types 'continue', send the next pending chunk."""
    key = (thread.guild.id, thread.id)
    if key in PENDING_REPLIES and PENDING_REPLIES[key]:
        next_chunk = PENDING_REPLIES[key].pop(0)
        if PENDING_REPLIES[key]:
            next_chunk += CONTINUE_HINT
        else:
            # All chunks consumed
            del PENDING_REPLIES[key]
        await thread.send(next_chunk)

async def generate_title(prompt: str) -> str:
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Return a short Discord thread title."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=12,
        temperature=0.6,
    )
    return resp.choices[0].message.content.strip().replace("\n", " ")[:40]

