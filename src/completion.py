# completion.py  –  SkippyAI edition: no moderation, 1900‑char chunks, /continue
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict
import os

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
#helper functions for Responses API
# --- add this near the top of completion.py ---
def _log_no_text_resp(resp, *, model: str, max_out: int, prompt_len: int) -> None:
    """Always log why a Responses call produced no user-visible text."""
    try:
        rid = getattr(resp, "id", None)
        status = getattr(resp, "status", None)
        inc = getattr(resp, "incomplete_details", None)
        inc_reason = getattr(inc, "reason", None) if inc else None

        usage = getattr(resp, "usage", None)
        it = getattr(usage, "input_tokens", None) if usage else None
        ot = getattr(usage, "output_tokens", None) if usage else None
        otd = getattr(usage, "output_tokens_details", None) if usage else None
        rtok = getattr(otd, "reasoning_tokens", None) if otd else None

        outs = getattr(resp, "output", None) or []
        out_types = [getattr(o, "type", None) for o in outs]

        logger.warning(
            "Responses no-text: id=%s model=%s status=%s incomplete=%s "
            "max_out=%s prompt_msgs=%s usage(in=%s out=%s reasoning=%s) out_types=%s",
            rid, model, status, inc_reason, max_out, prompt_len, it, ot, rtok, out_types,
        )
    except Exception as e:
        logger.exception(e)

# ──────────────────────────────────────────────────────────────
async def _responses_text(resp) -> str:
    """Extract plain text from Responses API objects across SDK versions."""
    # 1) Newer SDKs expose .output_text
    try:
        t = getattr(resp, "output_text", None)
        if t:
            return t
    except Exception:
        pass

    # 2) Older/mixed: resp.output[*].content[*] with type=output_text
    try:
        parts = getattr(resp, "output", None) or []
        out = []
        for p in parts:
            contents = getattr(p, "content", None) or []
            for c in contents:
                ctype = getattr(c, "type", None)
                if ctype in ("output_text", "text"):
                    txt = getattr(c, "text", None)
                    if txt:
                        out.append(txt)
        if out:
            return "".join(out)
    except Exception:
        pass

    # 3) No visible text — return empty so caller can decide (fallback/retry)
    return ""

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
    rendered_for_responses = [
        {"role": m["role"], "content": m["content"]}
        for m in rendered
    ]

    try:
        # Prefer Responses API; fall back to Chat Completions
        logger.info(f"Using Responses API with model {thread_config.model}")
        response = await client.responses.create(
            model=thread_config.model,
            input=rendered_for_responses,
            temperature=thread_config.temperature,
            max_output_tokens=thread_config.max_tokens,
        )
        reply = (await _responses_text(response)).strip()
        if not reply:
            _log_no_text_resp(
                response,
                model=thread_config.model,
                max_out=thread_config.max_tokens,
                prompt_len=len(rendered_for_responses),
            )
            logger.info("Falling back to Chat Completions because Responses returned no text.")
            # Perhaps reasoning-only output; let the existing fallback handle it
            raise RuntimeError("Responses produced no text")
        return CompletionData(CompletionResult.OK, reply, None)

    except openai.BadRequestError as e:
        if "maximum context length" in str(e):
            return CompletionData(CompletionResult.TOO_LONG, None, str(e))
        return CompletionData(CompletionResult.INVALID_REQUEST, None, str(e))

    except Exception as e:
        # Fallback to Chat Completions (support both param names)
        try:
            try:
                response = await client.chat.completions.create(
                    model=thread_config.model,
                    messages=rendered,
                    temperature=thread_config.temperature,
                    top_p=1.0,
                    max_completion_tokens=thread_config.max_tokens,
                    stop=["<|endoftext|>"],
                )
            except openai.BadRequestError as ee:
                if "max_completion_tokens" in str(ee) or "Unsupported parameter" in str(ee):
                    response = await client.chat.completions.create(
                        model=thread_config.model,
                        messages=rendered,
                        temperature=thread_config.temperature,
                        top_p=1.0,
                        max_tokens=thread_config.max_tokens,
                        stop=["<|endoftext|>"],
                    )
                else:
                    raise
            reply = response.choices[0].message.content.strip()
            return CompletionData(CompletionResult.OK, reply, None)
        except Exception as e2:
            logger.exception(e2)
            return CompletionData(CompletionResult.OTHER_ERROR, None, f"{e} / fallback: {e2}")


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
    """
    Create a Skippy‑style Discord thread title (<=40 chars).
    """
    # Use only the persona's first paragraph for flavour
    persona = BOT_INSTRUCTIONS.split("\n\n", 1)[0]

    system_msg = (
        f"{persona}\n\n"
        "Generate a *concise* (<=40 characters) Discord thread title that:\n"
        "• playfully belittles the human OR boasts about yourself, and\n"
        "• clearly hints at the technical topic in their prompt.\n"
        "No hashtags, no quotes, no trailing punctuation."
    )

    try:
        resp = await client.responses.create(
            model=os.getenv("OPENAI_MODEL_CHEAP", "gpt-5-mini"),
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            max_output_tokens=32,      # ~48 characters max
            temperature=0.7,
        )
        title = (await _responses_text(resp)).strip().replace("\n", " ")
    except Exception:
        try:
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                max_completion_tokens=16,
                temperature=0.7,
                top_p=0.9,
            )
        except openai.BadRequestError as ee:
            if "max_completion_tokens" in str(ee) or "Unsupported parameter" in str(ee):
                resp = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=16,
                    temperature=0.7,
                    top_p=0.9,
                )
            else:
                raise
        title = resp.choices[0].message.content.strip().replace("\n", " ")
    return title[:40]  # hard cap

