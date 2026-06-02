-- ============================================================================
-- Eve Migration 0002 — Chat-History + verschlüsselte Tokens
-- ============================================================================
--
-- Anwenden:
--   uv run python -m apps.dev.db_setup print --plain --file 0002_chat_and_tokens.sql
--   → Output in Supabase SQL Editor pasten → Run
-- ============================================================================

CREATE TYPE eve_message_source AS ENUM (
    'telegram',
    'cli',
    'web',
    'system'
);

-- ---------------------------------------------------------------------------
-- eve_chat_histories: Multi-Turn Memory pro Session
--
-- session_id-Konvention:
--   "TG_<telegram_user_id>"  → Telegram-User
--   "CLI_<profile_id>"        → CLI-User (eine Session pro Profil)
--   "WEB_<auth_id>"           → Web (später)
-- ---------------------------------------------------------------------------
CREATE TABLE eve_chat_histories (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT NOT NULL,
    profile_id  TEXT NOT NULL,
    source      eve_message_source NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_eve_chat_histories_session
    ON eve_chat_histories (session_id, created_at);
CREATE INDEX idx_eve_chat_histories_profile
    ON eve_chat_histories (profile_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- eve_tokens: verschlüsselte OAuth-Tokens (LinkedIn, später X, etc.)
--
-- Verschlüsselung passiert client-side (cryptography.Fernet) mit dem Master-Key
-- aus EVE_MASTER_KEY (in .env). Bytea-Spalten enthalten die rohen Cipher-Bytes.
-- Damit ist Supabase blind gegenüber den Klartext-Werten — selbst Admin-Access
-- zur DB enthüllt sie nicht ohne den Key.
-- ---------------------------------------------------------------------------
CREATE TABLE eve_tokens (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id             TEXT NOT NULL,
    provider               TEXT NOT NULL,                    -- 'linkedin', 'telegram', ...
    access_token_enc       BYTEA NOT NULL,                   -- Fernet-encrypted
    refresh_token_enc      BYTEA,                            -- nullable: nicht alle Provider haben Refresh
    expires_at             TIMESTAMPTZ,
    scope                  TEXT,                             -- z.B. "w_member_social r_liteprofile"
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ein Token pro (profile, provider) — alte Tokens werden überschrieben
CREATE UNIQUE INDEX idx_eve_tokens_profile_provider
    ON eve_tokens (profile_id, provider);

CREATE TRIGGER trg_eve_tokens_updated_at
    BEFORE UPDATE ON eve_tokens
    FOR EACH ROW EXECUTE FUNCTION eve_touch_updated_at();
