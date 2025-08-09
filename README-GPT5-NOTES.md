# GPT-5 Upgrade Notes

- **Core**: Migrated primary calls to the **Responses API** with a safe fallback to Chat Completions.
- **Models**: Default is `gpt-5`; added support for `gpt-5-mini` and `gpt-5-thinking`.
- **Thread titles**: Closing a thread now preserves the original title and swaps to the inactive prefix.
- **Summarization (optional)**: Flip `SUMMARIZATION_ENABLED=true` to enable running summaries when history is long.
- **Research (stub)**: `/research` command exists but is disabled until `RESEARCH_ENABLED=true` and tools are wired.
- **Stubs**: Added no-op scaffolding for meetings/voice, “ackshulley” mentor, and Linear integration. All behind env flags.

## Env flags
```
OPENAI_MODEL_DEFAULT=gpt-5
SUMMARIZATION_ENABLED=false
RESEARCH_ENABLED=false
MEETINGS_ENABLED=false
ACKSHULLEY_ENABLED=false
HISTORY_SUMMARY_TRIGGER_MESSAGES=80
```
