-- LLM Wiki — PostgreSQL schema
-- Run once: psql $DATABASE_URL -f db_init.sql

BEGIN;

-- ─── Tables ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pages (
    id              SERIAL      PRIMARY KEY,
    slug            TEXT        NOT NULL UNIQUE,  -- filename stem, e.g. "My_Page"
    relative_path   TEXT        NOT NULL UNIQUE,  -- e.g. "wiki/entities/My_Page.md"
    category        TEXT        NOT NULL,         -- entities | concepts | sources | synthesis | root
    title           TEXT,                         -- first H1 heading in body, if present
    created         DATE,                         -- from frontmatter
    updated         DATE,                         -- from frontmatter
    sources_count   INTEGER,                      -- from frontmatter "sources: N"
    raw_frontmatter JSONB,                        -- full parsed frontmatter (future-proof)
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS page_tags (
    id       SERIAL  PRIMARY KEY,
    page_id  INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    tag      TEXT    NOT NULL,
    UNIQUE (page_id, tag)
);

-- source_slug and target_slug are plain TEXT (not FKs) so forward references
-- to pages that don't exist yet are stored without constraint violations.
CREATE TABLE IF NOT EXISTS page_links (
    id           SERIAL PRIMARY KEY,
    source_slug  TEXT   NOT NULL,  -- slug of the page containing the link
    target_slug  TEXT   NOT NULL,  -- slug resolved from [[Wikilink]]
    UNIQUE (source_slug, target_slug)
);

-- ─── Indexes ─────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_pages_category ON pages (category);
CREATE INDEX IF NOT EXISTS idx_pages_updated  ON pages (updated DESC);
CREATE INDEX IF NOT EXISTS idx_page_tags_tag  ON page_tags (tag);
CREATE INDEX IF NOT EXISTS idx_links_source   ON page_links (source_slug);
CREATE INDEX IF NOT EXISTS idx_links_target   ON page_links (target_slug);

-- ─── Views ───────────────────────────────────────────────────────────────────

-- Broken links: wikilinks whose target page does not exist in the DB yet.
-- Use during Lint to find links that need fixing or new pages that need creating.
CREATE OR REPLACE VIEW broken_links AS
    SELECT pl.source_slug, pl.target_slug
    FROM   page_links pl
    LEFT JOIN pages p ON p.slug = pl.target_slug
    WHERE  p.id IS NULL;

-- Orphan pages: pages with no inbound links.
-- Excludes root-category files (index.md, log.md) which are not linked by convention.
CREATE OR REPLACE VIEW orphan_pages AS
    SELECT p.slug, p.relative_path, p.category
    FROM   pages p
    LEFT JOIN page_links pl ON pl.target_slug = p.slug
    WHERE  pl.id IS NULL
      AND  p.category != 'root';

-- Per-page link counts. Useful for spotting hub pages and isolated stubs.
CREATE OR REPLACE VIEW page_link_stats AS
    SELECT
        p.slug,
        p.category,
        COUNT(DISTINCT out_l.target_slug) AS outbound_links,
        COUNT(DISTINCT in_l.source_slug)  AS inbound_links
    FROM   pages p
    LEFT JOIN page_links out_l ON out_l.source_slug = p.slug
    LEFT JOIN page_links in_l  ON in_l.target_slug  = p.slug
    GROUP  BY p.slug, p.category;

COMMIT;
