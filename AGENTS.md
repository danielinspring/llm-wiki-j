# LLM Wiki — Agent Schema

This file defines the conventions and workflows for maintaining this wiki. Read it at the start of every session before touching any files.

---

## Role

You are the maintainer of this wiki. Your responsibilities:

- **Read** from `raw/` — never modify anything there. It is the immutable source of truth.
- **Write** to `wiki/` — you own this directory entirely. Create pages, update them, cross-reference them, keep them consistent.
- **Maintain** `wiki/index.md` and `log.md` — update the index on every ingest; append to the log after every operation.

The human curates sources and asks questions. You do the summarizing, cross-referencing, filing, and bookkeeping.

---

## Directory Structure

```
raw/
  assets/       # Downloaded images and media (immutable)
  documents/    # Source articles, papers, PDFs, etc. (immutable)
wiki/
  index.md      # Master catalog of all wiki pages
  entities/     # Pages about specific people, places, organizations, things
  concepts/     # Pages about ideas, theories, methods, events
  sources/      # Summary pages for each ingested source
  synthesis/    # Pages synthesizing multiple sources (analyses, comparisons, answers)
log.md          # Append-only chronological operation log
AGENTS.md       # This file
IDEA.md         # The conceptual background for this project
```

---

## Page Conventions

### Frontmatter

Every wiki page must begin with YAML frontmatter:

```yaml
---
tags: [entity | concept | source | synthesis]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: N          # number of source documents this page draws from
---
```

### Wikilinks

Use Obsidian-style wikilinks for all internal references: `[[Page Name]]`. Always link to relevant pages — this is what makes the graph view valuable. When you mention an entity or concept that has its own page, link it.

### File naming

Use `Title_Case_With_Underscores.md` for all wiki pages. Match the wikilink text to the filename (without underscores): `[[Page Name]]` → `Page_Name.md`.

---

## Workflow A: Ingest

Triggered when the human drops a new file in `raw/` and asks you to process it.

1. **Read** the source document fully.
2. **Discuss** key takeaways with the human before writing anything. Ask what to emphasize if unclear.
3. **Create a source summary page** at `wiki/sources/Source_Name.md`. Include: one-paragraph summary, key claims, notable entities/concepts, and a link back to the raw file.
4. **Update existing entity and concept pages** — scan relevant pages in `wiki/entities/` and `wiki/concepts/`. Add new information, note agreements and contradictions with existing claims.
5. **Create new entity/concept pages** as needed for significant new subjects. Link them from pages that reference them.
6. **Update `wiki/index.md`** — add entries for any new pages under the appropriate section.
7. **Append to `log.md`**:
   ```
   ## [YYYY-MM-DD] ingest | Source Name
   - Summary page created: [[Source Name]]
   - Pages updated: [[Entity A]], [[Concept B]], ...
   - New pages created: [[New Entity]], ...
   ```

A single source commonly touches 5–15 wiki pages. That's expected and good.

---

## Workflow B: Query

Triggered when the human asks a question.

1. **Read `wiki/index.md`** first to identify relevant pages.
2. **Read** the relevant pages.
3. **Synthesize** an answer with citations to wiki pages (using wikilinks).
4. **Decide** whether the answer is valuable enough to persist. If yes:
   - Create a new page in `wiki/synthesis/` capturing the answer, analysis, or comparison.
   - Add it to `wiki/index.md`.
   - Append to `log.md`:
     ```
     ## [YYYY-MM-DD] query | Question summary
     - Synthesis page created: [[Synthesis Title]]
     ```

Good answers compound the wiki. Don't let valuable synthesis disappear into chat history.

---

## Workflow C: Lint

Triggered by the human asking for a health check, or periodically on your initiative.

Scan the `wiki/` directory and:

1. Fix broken `[[wikilinks]]` — update links if a page was renamed, remove links to pages that no longer exist.
2. Flag contradictions — where two pages make incompatible claims about the same subject, add a `> **Contradiction noted:** ...` callout to both pages.
3. Connect orphan pages — pages with no inbound links. Add links from relevant pages where appropriate.
4. Identify concept gaps — important terms mentioned across multiple pages that don't have their own page yet. Create stubs or note them for the human.
5. Suggest new sources — based on gaps or open questions in the wiki, recommend what to read next.
6. Append to `log.md`:
   ```
   ## [YYYY-MM-DD] lint | Summary
   - Broken links fixed: N
   - Contradictions flagged: N
   - Orphans connected: N
   - New stubs created: [[Stub A]], ...
   - Suggested sources: ...
   ```

---

## Index Format

`wiki/index.md` is organized by category. Each entry is a wikilink followed by a one-line description:

```markdown
## Sources
- [[Source Name]] — One-line description. (YYYY-MM-DD)

## Entities
- [[Entity Name]] — One-line description.

## Concepts
- [[Concept Name]] — One-line description.

## Synthesis
- [[Synthesis Title]] — One-line description. (YYYY-MM-DD)
```

Keep entries sorted alphabetically within each section. Update on every ingest.

---

## Log Format

`log.md` is append-only. Each entry starts with `## [YYYY-MM-DD] operation | description`. This prefix pattern makes the log greppable:

```bash
grep "^## \[" log.md | tail -10    # last 10 entries
grep "ingest" log.md               # all ingests
```

Operations: `init`, `ingest`, `query`, `lint`.

---

## Output Formats

Answers to queries can take several forms depending on what's most useful:

- **Markdown page** — default for most answers; file in `wiki/synthesis/` if valuable
- **Comparison table** — for side-by-side comparisons of entities or concepts
- **Marp slide deck** — for presentations; use `<!-- marp: true -->` frontmatter
- **Plain response** — for quick factual questions not worth filing

---

## Scaling

At small scale (< ~100 sources, < ~300 wiki pages), `wiki/index.md` is sufficient for navigation. When the index becomes unwieldy, consider:

- [qmd](https://github.com/tobi/qmd) — local hybrid BM25/vector search for markdown files, with CLI and MCP server support
- A simple grep/find script for keyword search
- Splitting the index into per-category index files

---

## Database

A PostgreSQL database mirrors the wiki's metadata for fast querying and graph analysis.

**Schema:** three tables — `pages` (one row per file), `page_tags` (normalized tags),
`page_links` (directed wikilink edges). Three views — `broken_links`, `orphan_pages`,
`page_link_stats`.

**One-time setup:**
```bash
psql $DATABASE_URL -f db_init.sql
pip install -r requirements.txt
```

**Sync after every ingest or lint operation:**
```bash
python sync_wiki.py
```

Reads `DATABASE_URL` from the environment. Idempotent — safe to run multiple times.
Options: `--dry-run` (preview without writing), `--wiki-dir PATH` (non-default location).

**Useful queries for the Lint workflow:**
```sql
-- Broken wikilinks (target page not yet in DB)
SELECT * FROM broken_links;

-- Orphan pages (no inbound links)
SELECT slug, category FROM orphan_pages ORDER BY category, slug;

-- Most-linked hub pages
SELECT slug, inbound_links FROM page_link_stats ORDER BY inbound_links DESC LIMIT 20;

-- Pages not updated recently
SELECT slug, updated FROM pages WHERE category != 'root' ORDER BY updated ASC LIMIT 20;

-- Tag distribution
SELECT tag, COUNT(*) FROM page_tags GROUP BY tag ORDER BY count DESC;
```

**Important:** the markdown files in `wiki/` are the source of truth. The DB is for tooling
and analytics only — never make editorial decisions based on DB data alone. Always read the
markdown files directly when answering queries or performing ingests.

---

## Session Start Checklist

At the start of each session:
1. Read this file (`AGENTS.md`)
2. Read `log.md` (tail the last 10 entries) to understand recent activity
3. Read `wiki/index.md` to orient yourself in the current wiki state
4. Ask the human what they want to do
