# Eve — LinkedIn Editorial Agent

Eve ist ein eigenständiger LinkedIn-Redaktions-Agent in Python, der den bestehenden n8n-Workflow "Manni" ablöst. Statt einer visuellen Pipeline läuft Eve als Service mit klarer Hexagonal-Architektur (Ports & Adapters) — LLM, DB, Messaging und Storage sind hinter Protocols versteckt und einzeln austauschbar.

## Was Eve kann

- **Onboarding** in 8 Schritten — scrapt dein LinkedIn-Profil (Top-Performer aus Creator Analytics + Demographics + About) und leitet Themen, Audience-Beschreibung und Buyer-Personas via Claude ab
- **LinkedIn-Posts schreiben** im Stil des Kunden — 10 Hook-Varianten, iterative Verbesserung durch Persona-Feedback-Loops bis Score ≥7
- **Bilder generieren** über fal.ai (Seedream v4.5 / Nano Banana) mit konsistenter Identität via Referenzbildern aus Supabase Storage
- **Editorial Plan verwalten** — Posts in Supabase Postgres (oder JSON-Sidecar als Fallback)
- **Multi-Turn-Konversationen** — Chat-Memory persistent in Supabase
- **Briefings via CLI** (Stage 2 ✓) und Telegram (Stage 4, geplant)
- **Automatisch posten** zu festgelegten Terminen via Scheduler (Stage 3, geplant)

## Architektur

```
CLI / Telegram ──▶ IncomingMessage ──▶ Eve Agent ──▶ LLM (Anthropic Claude)
                                          │            │
                                          │            ├─▶ Tool-Loop:
                                          │            │   now, fetch_url,
                                          │            │   search/create/update_post,
                                          │            │   evaluate_with_persona,
                                          │            │   generate_image
                                          ▼            ▼
                            OutgoingMessage         Supabase
                                  │             (eve_posts,
                                  ▼              eve_chat_histories,
                            MessageRouter        eve_tokens)
                          (CLI / Telegram /         │
                           Web — by source)         ▼
                                                Storage Bucket
                                                (eve-media)
```

### Ports & Adapters

Alle externen Abhängigkeiten sind hinter Protocols in `src/eve/core/ports/` versteckt:

| Port              | Heute                                         | Morgen tauschbar gegen        |
|-------------------|-----------------------------------------------|-------------------------------|
| `LLMProvider`     | Anthropic Claude (mit Tool-Loop)              | OpenAI, OpenRouter, ...       |
| `PromptRepository`| Filesystem (`prompts/`)                       | Supabase, Notion, Git-Repo    |
| `PostsRepository` | Supabase Postgres / Filesystem-Fallback       | Baserow, NocoDB, Airtable     |
| `ChatMemory`      | Supabase / In-Memory-Fallback                 | Redis, Postgres-Hist          |
| `FileStorage`     | Supabase Storage                              | S3, Backblaze, lokal          |
| `ImageGenerator`  | fal.ai Seedream / Nano Banana                 | OpenAI Images, Replicate      |
| `LinkedInProfileFetcher` | Playwright (persistent_context) + GDPR-Export | Proxycurl & Co. (tot)  |
| `MessagingProvider` | CLI (Rich-basiert)                          | Telegram, Slack, Mattermost   |
| `SocialPublisher` | (noch nicht implementiert)                    | LinkedIn, X, Threads          |

Adapter werden ausschliesslich im **Composition Root** (`src/eve/config/container.py` / `apps/cli/cmd_run.py`) verdrahtet. Core-Code importiert nie einen Adapter direkt.

## Projekt-Struktur

```
.
├── apps/
│   ├── cli/           # zentrale `eve` CLI (Typer) — onboard, run, db, profile, image
│   ├── dev/           # einzelne Helper-Tools (preview_prompts, test_image_gen, ...)
│   ├── onboarding/    # Wizard-CLI + Rich-UI Adapter
│   ├── api/           # FastAPI (Telegram Webhook, Stage 4)
│   └── worker/        # Scheduler (Stage 3)
├── src/eve/
│   ├── core/          # Domain — ports, entities, use cases (pure Python)
│   ├── adapters/      # Konkrete Implementierungen (LLM, Persistence, LinkedIn, ...)
│   ├── agent/         # Eve Agent + Tools (now, fetch_url, posts CRUD, persona, image)
│   ├── ingestion/     # PDF/Audio/Image/Excel Extraction (Stage 4)
│   ├── utils/         # Windows-Console, Crypto (Fernet)
│   └── config/        # Settings + DI-Container
├── migrations/        # SQL — main.sql (idempotent setup) + 0001/0002 (history)
├── prompts/
│   ├── templates/     # Jinja2-Templates (eve_system, persona, wizard_*)
│   └── profiles/      # Pro Kunde ein YAML + .posts.json Sidecar
└── tests/             # pytest (62 Tests grün)
```

## Setup

### Voraussetzungen

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) Package Manager
- Anthropic API Key
- Supabase (Free Tier reicht) + fal.ai API Key — optional, mit eleganten Fallbacks

### Installation

```bash
# 1. Dependencies installieren (zieht Playwright + Chromium mit)
uv sync
uv run playwright install chromium

# 2. .env vorbereiten
cp .env.example .env
# → mindestens ANTHROPIC_API_KEY eintragen
# → für Supabase: SUPABASE_URL + SUPABASE_SERVICE_KEY
# → für Bildgenerierung: FAL_API_KEY

# 3. Eve installiert sich als CLI
uv run eve --help

# 4. (optional) Supabase einrichten
uv run eve db check                # Connection-Smoke-Test
uv run eve db migrate --open       # Öffnet SQL Editor im Browser
uv run eve db print --plain        # SQL in Clipboard pipen
# → Im Supabase SQL Editor pasten → Run

# 5. Storage-Bucket "eve-media" mit Folder "references/" anlegen
#    Im Supabase Dashboard → Storage → New bucket (public read)
#    Folder "references/" → 4-8 Portraits von dir hochladen
```

### Erste Schritte

```bash
# Onboarding durchlaufen (8 Steps)
uv run eve onboard --profile danny

# Profile-Assets verifizieren
uv run eve profile verify

# Mit Eve chatten
uv run eve run
```

### `eve` CLI im Überblick

```
eve onboard            # 8-Step Wizard durchlaufen
eve run                # Hauptprozess (CLI-Chat mit Agent + Tools)
eve version            # Version anzeigen

eve db check           # Supabase: Verbindung, Bucket, References, Tabelle
eve db migrate         # SQL-Editor-Link + Setup-Anleitung
eve db print --plain   # SQL ins Clipboard

eve profile verify     # Asset-Check für Profil
eve profile preview    # System-Prompts (Eve + Persona) im Detail
eve profile personas   # Buyer-Personas neu generieren

eve image test         # fal.ai Bildgenerierung mit Astronaut-Default-Prompt
eve image test --model fal-ai/nano-banana/edit --open
```

### Tests

```bash
uv run python -m pytest tests/
uv run ruff check src/ apps/ tests/
```

## Konfiguration

| Variable | Zweck | Pflicht? |
|----------|-------|----------|
| `ANTHROPIC_API_KEY` | Claude für Agent + Wizard | ✓ |
| `EVE_LLM_DEFAULT_MODEL` | z.B. `claude-opus-4-7` / `claude-sonnet-4-7` | default ok |
| `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` | Persistenz für Posts, History, Storage | optional → Filesystem-Fallback |
| `FAL_API_KEY` | Bildgenerierung | optional → kein Image-Tool |
| `FAL_IMAGE_MODEL` | z.B. `fal-ai/bytedance/seedream/v4.5/edit` | default ok |
| `EVE_MASTER_KEY` | Fernet-Key für OAuth-Token-Verschlüsselung | für LinkedIn-Stage |
| `TELEGRAM_BOT_TOKEN` | Bot-Integration | für Telegram-Stage |
| `LINKEDIN_CLIENT_ID` + `..._SECRET` | OAuth-App | für LinkedIn-Stage |

## Status

| Komponente                         | Status |
|------------------------------------|--------|
| Hexagonal-Architektur (Core, Ports & Adapters) | ✅ |
| 8-Step Onboarding-Wizard (Scraper + Manual)    | ✅ |
| LinkedIn-Scraping (Playwright + GDPR-Export)   | ✅ |
| Anthropic Claude LLM-Adapter mit Tool-Loop     | ✅ |
| Eve Agent + 7 Tools (now, fetch_url, posts CRUD, persona, image) | ✅ |
| fal.ai Bildgenerierung (Seedream + Nano Banana)| ✅ |
| Persona Sub-Agent (Buyer-Avatar-Feedback)      | ✅ |
| MessageRouter (CLI / Telegram / Web)           | ✅ |
| Supabase-Adapter (Posts, ChatMemory, Storage)  | ✅ |
| Setup-SQL (`main.sql`, idempotent)             | ✅ |
| CLI-Konsolidierung (`eve` mit Sub-Commands)    | ✅ |
| Image-Persistierung (fal.ai → Supabase Storage)| ✅ |
| `eve run --mode chat` mit echtem Agent         | ✅ |
| Telegram-Adapter (multimodal: Voice/Image/PDF) | ⏳ Stage 4 |
| LinkedIn OAuth + Auto-Post-Scheduler           | ⏳ Stage 3 |
| Web-GUI (Admin-Dashboard + Chat-Frontend)      | ⏳ Stage 5 |

## Roadmap

**Stage 3 — LinkedIn-Posting (geplant)**
- OAuth-Flow via Browser + Callback-Server
- Token-Persistenz in `eve_tokens` (Fernet-encrypted)
- `LinkedInPublisher` Adapter (REST gegen `linkedin.com/v2`)
- APScheduler-Job: täglich `eve_posts WHERE status=ready AND scheduled_for=today`

**Stage 4 — Telegram Multi-Modal (geplant)**
- `TelegramMessenger` als MessagingProvider
- Bot-Setup im Wizard (Step 7 ist heute Mock)
- Ingestion-Pipeline: Voice → Whisper, Image → Claude-Vision, PDF → pypdf, Excel → openpyxl
- Webhook (FastAPI) für Production, Long-Polling für Dev

**Stage 5 — Web-GUI (Roadmap)**
- Editorial-Plan-Dashboard (Posts-Liste mit Status-Filter, Approval-UI)
- Chat-Frontend für Eve (parallel zur CLI, gleicher MessageRouter)
- Profile-Editor mit Live-Preview der gerenderten System-Prompts
- Stack-Vorschlag: Next.js + Supabase Auth + dieselbe FastAPI als Backend

## Migration von n8n

Der Original-n8n-Workflow (`Lego - Manni2`) bleibt parallel als Referenz aktiv, bis Eve produktionsreif ist. Reihenfolge der Migration:

1. ✅ **Onboarding + Agent + Posts** — Eve schreibt Posts via CLI in `eve_posts`
2. ✅ **Bildgenerierung** identisch zu n8n repliziert (Seedream-Pipeline + Referenzbilder)
3. ⏳ **LinkedIn-Posting + Scheduler** auf Test-Profil — Stage 3
4. ⏳ **Telegram-Bot** parallel zum n8n-Slack-Workflow — Stage 4
5. ⏳ **Web-GUI** für Editorial Plan + Chat — Stage 5
6. n8n-Workflow deaktivieren

## Repository

[github.com/bizrockman/LinkedinRedakteur](https://github.com/bizrockman/LinkedinRedakteur)
