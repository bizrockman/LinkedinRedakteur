# Eve — LinkedIn Editorial Agent

Eve ist ein eigenständiger LinkedIn-Redaktions-Agent, der den bestehenden n8n-Workflow "Manni" ablöst. Statt einer visuellen Pipeline läuft Eve als Python-Service mit klarer Hexagonal-Architektur (Ports & Adapters), sodass DB- und LLM-Provider austauschbar sind.

## Was Eve kann

- **Briefings entgegennehmen** via Telegram (Phase 1), Slack/Mattermost (Phase 2)
- **Multi-Modal-Input** verarbeiten: Text, Audio (Whisper), Bilder (Vision), PDF, Excel
- **LinkedIn-Posts schreiben** im Stil des Kunden — inklusive 10 Hook-Varianten und iterativer Verbesserung durch Synthetic Personas
- **Bilder generieren** über fal.ai (Seedream v4.5) mit konsistenter Identität via Referenzbildern
- **Editorial Plan verwalten** in Supabase Postgres (eve-Schema)
- **Automatisch posten** zu festgelegten Terminen via Scheduler

## Architektur

```
Telegram/Slack ──▶ FastAPI Webhook ──▶ Eve Agent ──▶ LLM (Claude/OpenAI/OpenRouter)
                                          │            │
                                          │            └─▶ Tools: Posts CRUD, Persona, Image-Gen, Web-Fetch
                                          │
                                          ├─▶ Supabase (posts, chat_histories, media)
                                          └─▶ Supabase Storage (creatives)

Scheduler ──▶ Supabase Query (status=ready, date=today) ──▶ LinkedIn API
```

### Ports & Adapters

Alle externen Abhängigkeiten sind hinter Protocols in `src/eve/core/ports/` versteckt:

| Port              | Heute             | Morgen tauschbar gegen        |
|-------------------|-------------------|-------------------------------|
| `LLMProvider`     | Anthropic Claude  | OpenAI, OpenRouter, ...       |
| `PromptRepository`| Filesystem (`prompts/`) | Supabase, Notion, Git-Repo |
| `PostsRepository` | Supabase Postgres | Baserow, NocoDB, Airtable     |
| `LinkedInProfileFetcher` | Playwright (stealth) + GDPR-Export-Parser | Proxycurl & Co. (tot) |
| `MessagingProvider` | Telegram        | Slack, Mattermost, Rocket.Chat |
| `ImageGenerator`  | fal.ai Seedream   | OpenAI Images, Replicate       |
| `FileStorage`     | Supabase Storage  | S3, Backblaze, lokal           |
| `SocialPublisher` | LinkedIn          | X, Threads, Mastodon           |

Adapter werden ausschliesslich im **Composition Root** (`src/eve/config/container.py`) verdrahtet. Core-Code importiert nie einen Adapter direkt.

## Projekt-Struktur

```
.
├── apps/
│   ├── api/           # FastAPI: Webhooks (Telegram), Health, Cron-Endpoints
│   └── worker/        # APScheduler: täglicher Publisher-Job, fal.ai-Polling
├── src/eve/
│   ├── core/          # Domain — ports, entities, use cases (pure Python)
│   ├── adapters/      # Konkrete Implementierungen (LLM, DB, Telegram, ...)
│   ├── agent/         # Eve Agent: System-Prompt, Tools, Conversation Loop
│   ├── ingestion/     # PDF/Audio/Image/Excel Extraction
│   └── config/        # Settings + DI-Container
├── migrations/        # SQL für Supabase (eve-Schema)
├── prompts/           # Externalisierte Prompts
│   ├── templates/     # Jinja2-Templates (eve_system.md.j2, persona.md.j2)
│   └── profiles/      # Kundenspezifische Daten (YAML)
└── tests/             # pytest
```

## Setup

### Voraussetzungen

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) Package Manager
- Zugang zu einer Supabase-Instanz (Postgres + Storage)
- API-Keys: Anthropic (oder OpenAI/OpenRouter), Telegram Bot, fal.ai, LinkedIn

### Installation

```bash
# 1. Dependencies installieren
uv sync

# 2. .env vorbereiten
cp .env.example .env
# → Werte ausfüllen

# 3. Supabase Free-Tier Projekt anlegen
#    → https://supabase.com/dashboard → New Project
#    → Settings → Database → Connection String (URI, Transaction Pool)
#    → SUPABASE_DB_URL in .env eintragen

# 4. DB-Schema anwenden
uv run python -m apps.dev.db_setup check     # Connection-Smoke-Test
uv run python -m apps.dev.db_setup status    # zeigt Migration-Plan (dry-run)
uv run python -m apps.dev.db_setup migrate   # wendet alle pending Migrations an

# 5. Supabase Storage Bucket "eve-media" anlegen
#    (im Supabase Dashboard, public read)

# 6. Telegram Webhook setzen (sobald die API läuft)
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=<EVE_PUBLIC_URL>/telegram"
```

### DB-Setup im Detail

Der Migration-Runner (`apps/dev/db_setup.py`) hat drei Sub-Commands:

| Command | Was es tut |
|---|---|
| `check` | Verbindungs-Smoke-Test gegen die DB |
| `status` | Zeigt welche Migrations da sind / schon liefen (dry-run, schreibt nichts) |
| `migrate` | Wendet alle ausstehenden Migrations innerhalb von Transaktionen an |

Tracking via `eve.schema_migrations` Tabelle mit SHA-256-Hash pro Datei. Bei Drift (eine bereits angewendete SQL-Datei wurde nachträglich verändert) stoppt der Runner mit `checksum_mismatch`-Hinweis — kein Auto-Re-Apply.

Migration-Files liegen in `migrations/*.sql`. Neue hinzufügen: einfach `0002_xxx.sql` anlegen, Runner picks it up.

### Lokal starten

```bash
# API Server
uv run uvicorn apps.api.main:app --reload --port 8000

# Scheduler / Worker (separat)
uv run python -m apps.worker.scheduler
```

### Tests

```bash
uv run pytest
uv run ruff check .
uv run mypy src/
```

## Konfiguration: LLM-Provider tauschen

Standard-Provider in `.env`:

```bash
EVE_LLM_DEFAULT_PROVIDER=anthropic   # | openai | openrouter
EVE_LLM_DEFAULT_MODEL=claude-opus-4-7
```

Bei OpenRouter kann der zugrundeliegende Provider pro Call gepinnt werden (siehe `openrouter_provider.py`).

## Status

| Komponente              | Status |
|-------------------------|--------|
| Schema + Entities       | ✅ |
| Ports & Container       | ✅ |
| Supabase Adapter        | ⏳ |
| Anthropic LLM Adapter   | ⏳ |
| Telegram Webhook        | ⏳ |
| Eve Agent + Tools       | ⏳ |
| fal.ai Image Generation | ⏳ |
| LinkedIn Publisher      | ⏳ |
| Scheduler               | ⏳ |
| Admin Dashboard (Next)  | ⏳ |

## Migration von n8n

Der Original-n8n-Workflow (`Lego - Manni2`) bleibt parallel als Referenz aktiv, bis Eve vollständig funktioniert. Reihenfolge der Migration:

1. **Datenbank** zuerst — Posts-Tabelle in Supabase synchronisieren
2. **Agent-Core + LLM** in Isolation testen (CLI-Replay alter Briefings)
3. **Telegram Adapter** parallel betreiben
4. **Image Generation** identisch zu n8n replizieren (gleiche Referenzbilder)
5. **LinkedIn Publisher + Scheduler** zuletzt — erst auf Test-Profil
6. n8n-Workflow deaktivieren
