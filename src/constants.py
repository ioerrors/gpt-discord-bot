"""
constants.py  —  SkippyAI stripped-down edition
No moderation • zero extra delay • 1 900-char chunks • GPT-5 default models
"""

from dotenv import load_dotenv
import os, yaml, dacite
from typing import List, Dict, Literal

from src.base import Config

load_dotenv()

# ───────────────────────────────────────────────────────────────
# Load persona from config.yaml
# ───────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG: Config = dacite.from_dict(
    Config,
    yaml.safe_load(open(os.path.join(SCRIPT_DIR, "config.yaml"), "r")),
)

BOT_NAME         = CONFIG.name
BOT_INSTRUCTIONS = CONFIG.instructions
EXAMPLE_CONVOS   = CONFIG.example_conversations

# ───────────────────────────────────────────────────────────────
# Environment variables
# ───────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
DISCORD_CLIENT_ID = os.environ["DISCORD_CLIENT_ID"]
OPENAI_API_KEY    = os.environ["OPENAI_API_KEY"]

# Prefer new var; fall back to old so we don't break existing envs
OPENAI_MODEL_DEFAULT = os.getenv("OPENAI_MODEL_DEFAULT")
DEFAULT_MODEL = OPENAI_MODEL_DEFAULT or os.getenv("DEFAULT_MODEL", "gpt-5")

ALLOWED_SERVER_IDS: List[int] = [
    int(s) for s in os.environ["ALLOWED_SERVER_IDS"].split(",")
]

# Moderation mapping kept only for future use; not referenced now
SERVER_TO_MOD_CHANNEL: Dict[int, int] = {}

# ───────────────────────────────────────────────────────────────
# Allowed OpenAI models
# ───────────────────────────────────────────────────────────────
ALLOWED_MODELS = {
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-thinking",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4",
    "gpt-3.5-turbo",
}

AVAILABLE_MODELS = Literal[
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-thinking",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4",
    "gpt-3.5-turbo",
]

# ───────────────────────────────────────────────────────────────
# Discord bot invite (Send Msgs • Threads • Slash Cmds)
# ───────────────────────────────────────────────────────────────
BOT_INVITE_URL = (
    "https://discord.com/api/oauth2/authorize"
    f"?client_id={DISCORD_CLIENT_ID}"
    "&permissions=328565073920&scope=bot"
)

# ───────────────────────────────────────────────────────────────
# Runtime / UX tuning
# ───────────────────────────────────────────────────────────────
SECONDS_DELAY_RECEIVING_MSG = 0        # respond immediately
MAX_THREAD_MESSAGES         = 1000     # auto-close after this many
MAX_CHARS_PER_REPLY_MSG     = 1900     # Discord hard limit is 2000

ACTIVATE_THREAD_PREFX    = "💬✅"   # (intentional spelling kept)
INACTIVATE_THREAD_PREFIX = "💬❌"

# ───────────────────────────────────────────────────────────────
# Feature flags (all default OFF)
# ───────────────────────────────────────────────────────────────
SUMMARIZATION_ENABLED = os.getenv("SUMMARIZATION_ENABLED", "false").lower() == "true"
RESEARCH_ENABLED      = os.getenv("RESEARCH_ENABLED", "false").lower() == "true"
MEETINGS_ENABLED      = os.getenv("MEETINGS_ENABLED", "false").lower() == "true"
ACKSHULLEY_ENABLED    = os.getenv("ACKSHULLEY_ENABLED", "false").lower() == "true"

# Summarization thresholds
HISTORY_SUMMARY_TRIGGER_MESSAGES = int(os.getenv("HISTORY_SUMMARY_TRIGGER_MESSAGES", "80"))
