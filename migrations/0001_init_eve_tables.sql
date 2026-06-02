-- ============================================================================
-- Eve Schema — Minimum für n8n-Parität
-- ============================================================================
--
-- Eine Tabelle, zwei Enums, drei Indizes. Mehr nicht.
--
-- "metadata JSONB" ist die Catch-All-Spalte für alles was noch nicht oft genug
-- gefiltert wird, um eine eigene Spalte zu rechtfertigen:
--   persona_score, persona_feedback, engagement {likes,comments,reposts,...},
--   topic_tags, creative_prompt, linkedin_post_id, error_message, ...
--
-- Wird ein Feld später "first-class" (häufig gefiltert/sortiert), promoten wir
-- es per neuer Migration (0002_xxx.sql).
--
-- Anwenden:
--   1. https://supabase.com/dashboard/project/<ref>/sql/new
--   2. SQL einfügen (`uv run python -m apps.dev.db_setup print --plain`)
--   3. Run
-- ============================================================================

CREATE TYPE eve_post_status AS ENUM (
    'draft',      -- Eve generated, awaiting human approval
    'ready',      -- Approved by user, scheduled for posting
    'posted',     -- Successfully published (or imported as historic)
    'error',      -- Posting failed
    'archived'    -- Manually archived / deprecated
);

CREATE TYPE eve_post_source AS ENUM (
    'eve',              -- Von Eve generiert
    'linkedin_import',  -- Playwright-Scrape (Onboarding / Refresh)
    'gdpr_import',      -- DSGVO-Datenexport
    'manual_import'     -- User-Paste via Wizard / Chat
);

CREATE TABLE eve_posts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id     TEXT NOT NULL,                    -- referenziert prompts/profiles/<id>.yaml
    text           TEXT NOT NULL,
    status         eve_post_status NOT NULL DEFAULT 'draft',
    source         eve_post_source NOT NULL DEFAULT 'eve',

    scheduled_for  TIMESTAMPTZ,
    posted_at      TIMESTAMPTZ,

    creative_url   TEXT,                             -- Bild-URL (Supabase Storage / fal.ai)
    linkedin_url   TEXT,                             -- Permalink importierter Posts

    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Scheduler-Query: "Status=ready AND scheduled_for=today"
CREATE INDEX idx_eve_posts_scheduled_for
    ON eve_posts (scheduled_for) WHERE status = 'ready';

-- Liste pro Profil + Status (Editorial-Plan-View)
CREATE INDEX idx_eve_posts_profile_status
    ON eve_posts (profile_id, status);

-- Idempotent Re-Import: gleiche LinkedIn-URL nicht doppelt schreiben
CREATE UNIQUE INDEX idx_eve_posts_linkedin_url
    ON eve_posts (profile_id, linkedin_url) WHERE linkedin_url IS NOT NULL;

-- updated_at automatisch pflegen
CREATE OR REPLACE FUNCTION eve_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_eve_posts_updated_at
    BEFORE UPDATE ON eve_posts
    FOR EACH ROW EXECUTE FUNCTION eve_touch_updated_at();
