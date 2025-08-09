# SkippyAI — Discord Bot (GPT‑5)

Small, opinionated Discord bot for technical chats on Discord. Uses OpenAI’s **Responses API** by default (with a compatible fallback) and creates tidy thread-based conversations.

---

## Please read (upstream resources)
- **Problems running this template:** [Discord Project Post](https://discord.com/channels/974519864045756446/1055336272543092757)
- **General OpenAI API questions:** [Discord API Discussions](https://discord.com/channels/974519864045756446/1037561178286739466)
- **Template bugs:** open an Issue on your fork
- **Feature requests:** fork and build; upstream template isn’t accepting new features

---

## Overview
- `/chat` starts a public thread and replies to each message in that thread.
- The whole thread is sent to the model each turn (conversation memory).
- Long outputs are paginated; type `continue` to receive the next chunk.
- When limits are reached, the thread is closed cleanly (title preserved).
- Persona/instructions live in `src/config.yaml`.
- Default model is **`gpt-5`** (configurable).

## Requirements
- Python **3.10+** (3.11 recommended)
- Discord application (bot token + Application ID)
- OpenAI API key
- Dependencies in `requirements.txt` (notably `openai` and `discord.py`)

## Quick start (local)
1. Copy `.env.example` → `.env` and fill in tokens/IDs.
2. Install deps:
   ```bash
   pip install -r requirements.txt
   ```
3. Run:
   ```bash
   python -m src.main
   ```
4. Use the printed invite URL to add the bot to your server, then run `/chat`.

## Configuration
Environment variables (see `.env.example`):
```
OPENAI_API_KEY=...
DISCORD_BOT_TOKEN=...
DISCORD_CLIENT_ID=...           # Application ID
ALLOWED_SERVER_IDS=123,456      # comma‑separated server (guild) IDs

# Preferred default model (falls back to DEFAULT_MODEL if present)
OPENAI_MODEL_DEFAULT=gpt-5
# DEFAULT_MODEL=gpt-5

# Feature flags (all default OFF)
SUMMARIZATION_ENABLED=false
RESEARCH_ENABLED=false
MEETINGS_ENABLED=false
ACKSHULLEY_ENABLED=false

# Optional summarization threshold
HISTORY_SUMMARY_TRIGGER_MESSAGES=80
```

You can customize the persona and examples in `src/config.yaml`.

## Commands
### `/chat`
- Options: `model`, `temperature`, `max_tokens` (sane defaults provided)
- Creates a thread titled from your prompt and continues within that thread.

### `/research` (stub)
- Disabled by default; enable via `RESEARCH_ENABLED=true` when ready to wire tools.

## Deploying (Render example)
- **Service type:** Background Worker
- **Branch:** choose your deployment branch (e.g., `main` or a staging branch)
- **Build:** `pip install -r requirements.txt`
- **Start:** `python -m src.main`
- **Environment:** Python 3.11
- Add your env vars in the dashboard (no quotes).

## Contributing
This fork aims to stay small and practical. Bug fixes welcome in your repo; feature work should live on a fork per your needs.

## License
See upstream template’s license; modifications in this fork follow the same terms.
