-- ============================================================================
-- Eve Schema Setup — ALLES in einem File
-- ============================================================================
--
-- Das ist die einzige Datei die du in Supabase einspielen musst:
--
--   1. Im Dashboard:  Settings → SQL Editor → "New query"
--      Deep-Link:     https://supabase.com/dashboard/project/<ref>/sql/new
--
--   2. Dieses SQL via `uv run eve db print --plain` ins Clipboard, paste'n
--
--   3. "Run" klicken
--
-- Idempotent: kann mehrfach laufen, ohne kaputt zu gehen.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Enums
-- ----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE eve_post_status AS ENUM (
        'draft',      -- Eve generated, awaiting human approval
        'ready',      -- Approved by user, scheduled for posting
        'posted',     -- Successfully published (or imported as historic)
        'error',      -- Posting failed
        'archived'    -- Manually archived / deprecated
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE eve_post_source AS ENUM (
        'eve',              -- Von Eve generiert
        'linkedin_import',  -- Playwright-Scrape (Onboarding / Refresh)
        'gdpr_import',      -- DSGVO-Datenexport
        'manual_import'     -- User-Paste via Wizard / Chat
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE eve_message_source AS ENUM (
        'telegram',
        'cli',
        'web',
        'system'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Wenn der Type bereits aus einer früheren Version existiert, ggf. fehlende
-- Werte nachziehen. ALTER TYPE ADD VALUE IF NOT EXISTS ist seit Postgres 9.6
-- verfügbar und idempotent — kann beliebig oft laufen.
ALTER TYPE eve_message_source ADD VALUE IF NOT EXISTS 'telegram';
ALTER TYPE eve_message_source ADD VALUE IF NOT EXISTS 'cli';
ALTER TYPE eve_message_source ADD VALUE IF NOT EXISTS 'web';
ALTER TYPE eve_message_source ADD VALUE IF NOT EXISTS 'system';

-- Selbiges Sicherheits-Netz für die anderen Enums:
ALTER TYPE eve_post_status ADD VALUE IF NOT EXISTS 'draft';
ALTER TYPE eve_post_status ADD VALUE IF NOT EXISTS 'ready';
ALTER TYPE eve_post_status ADD VALUE IF NOT EXISTS 'posted';
ALTER TYPE eve_post_status ADD VALUE IF NOT EXISTS 'error';
ALTER TYPE eve_post_status ADD VALUE IF NOT EXISTS 'archived';

ALTER TYPE eve_post_source ADD VALUE IF NOT EXISTS 'eve';
ALTER TYPE eve_post_source ADD VALUE IF NOT EXISTS 'linkedin_import';
ALTER TYPE eve_post_source ADD VALUE IF NOT EXISTS 'gdpr_import';
ALTER TYPE eve_post_source ADD VALUE IF NOT EXISTS 'manual_import';

-- ----------------------------------------------------------------------------
-- eve_posts — Editorial Plan + historisches Archiv
--
-- `source = 'eve'`           → Eve hat ihn geschrieben, durchläuft Pipeline
-- `source = 'linkedin_*'/...` → historisch importiert (status meist 'posted')
-- Catch-all `metadata` JSONB für engagement, persona_score, topic_tags, etc.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eve_posts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id     TEXT NOT NULL,                    -- referenziert prompts/profiles/<id>.yaml
    text           TEXT NOT NULL,
    status         eve_post_status NOT NULL DEFAULT 'draft',
    source         eve_post_source NOT NULL DEFAULT 'eve',

    scheduled_for  TIMESTAMPTZ,
    posted_at      TIMESTAMPTZ,

    creative_url   TEXT,                             -- Bild-URL (Supabase Storage / fal.ai-CDN)
    linkedin_url   TEXT,                             -- Permalink importierter Posts

    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eve_posts_scheduled_for
    ON eve_posts (scheduled_for) WHERE status = 'ready';

CREATE INDEX IF NOT EXISTS idx_eve_posts_profile_status
    ON eve_posts (profile_id, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_eve_posts_linkedin_url
    ON eve_posts (profile_id, linkedin_url) WHERE linkedin_url IS NOT NULL;

-- ----------------------------------------------------------------------------
-- eve_chat_histories — Multi-Turn Memory pro Session
--
-- session_id-Konvention:
--   "TG_<telegram_user_id>"   → Telegram-User
--   "CLI_<profile_id>"         → CLI-User
--   "WEB_<auth_id>"            → Web (später)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eve_chat_histories (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    profile_id  TEXT NOT NULL,
    source      eve_message_source NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eve_chat_histories_session
    ON eve_chat_histories (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_eve_chat_histories_profile
    ON eve_chat_histories (profile_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- eve_tokens — verschlüsselte OAuth-Tokens (LinkedIn, etc.)
--
-- Verschlüsselung passiert client-side (Python cryptography.Fernet) mit dem
-- Master-Key aus EVE_MASTER_KEY (in .env). Bytea-Spalten enthalten Cipher-Bytes.
-- Damit ist Supabase blind gegenüber den Klartext-Werten.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eve_tokens (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id             TEXT NOT NULL,
    provider               TEXT NOT NULL,                    -- 'linkedin', 'telegram', ...
    access_token_enc       BYTEA NOT NULL,                   -- Fernet-encrypted
    refresh_token_enc      BYTEA,
    expires_at             TIMESTAMPTZ,
    scope                  TEXT,
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_eve_tokens_profile_provider
    ON eve_tokens (profile_id, provider);

-- ----------------------------------------------------------------------------
-- updated_at Trigger (auto-pflegt das Feld bei jedem UPDATE)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION eve_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eve_posts_updated_at ON eve_posts;
CREATE TRIGGER trg_eve_posts_updated_at
    BEFORE UPDATE ON eve_posts
    FOR EACH ROW EXECUTE FUNCTION eve_touch_updated_at();

DROP TRIGGER IF EXISTS trg_eve_tokens_updated_at ON eve_tokens;
CREATE TRIGGER trg_eve_tokens_updated_at
    BEFORE UPDATE ON eve_tokens
    FOR EACH ROW EXECUTE FUNCTION eve_touch_updated_at();
