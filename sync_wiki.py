#!/usr/bin/env python3
"""
sync_wiki.py — Sync wiki markdown metadata to PostgreSQL.

Walks all .md files under wiki/ (and log.md at the project root),
parses YAML frontmatter and [[wikilinks]], then upserts rows into the
pages / page_tags / page_links tables. Purges rows for files no longer
on disk. Runs in a single transaction for atomicity.

Usage:
    python sync_wiki.py [--dry-run] [--wiki-dir PATH]

Environment:
    DATABASE_URL  PostgreSQL connection string (required)
                  e.g. postgresql://user:pass@localhost:5432/llm_wiki

Setup (one-time):
    psql $DATABASE_URL -f db_init.sql
    pip install -r requirements.txt
"""

import json
import os
import re
import sys
from pathlib import Path

import frontmatter
import psycopg2
import psycopg2.extras

# ─── Connection ──────────────────────────────────────────────────────────────

def get_connection():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit(
            "ERROR: DATABASE_URL environment variable is not set.\n"
            "Example: export DATABASE_URL=postgresql://user:pass@localhost:5432/llm_wiki"
        )
    return psycopg2.connect(url)


# ─── Parsing helpers ─────────────────────────────────────────────────────────

def parse_slug(filepath: str, project_root: str) -> str:
    """Return the bare filename stem (no directory, no extension).

    wiki/entities/My_Page.md -> 'My_Page'
    log.md                   -> 'log'
    """
    return Path(filepath).stem


def parse_category(filepath: str, project_root: str) -> str:
    """Infer category from the file's parent directory name.

    wiki/entities/  -> 'entities'
    wiki/concepts/  -> 'concepts'
    wiki/sources/   -> 'sources'
    wiki/synthesis/ -> 'synthesis'
    anything else   -> 'root'
    """
    known = {"entities", "concepts", "sources", "synthesis"}
    parent = Path(filepath).parent.name
    return parent if parent in known else "root"


def extract_title(body: str):
    """Return text of the first H1 heading, or None."""
    match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    return match.group(1).strip() if match else None


def extract_wikilinks(body: str):
    """Return sorted list of unique slugs referenced by [[Wikilink]] syntax.

    Handles:
        [[Page Name]]              -> 'Page_Name'
        [[Page Name|display text]] -> 'Page_Name'
        [[Page Name#section]]      -> 'Page_Name'
    """
    pattern = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
    slugs = set()
    for match in pattern.finditer(body):
        raw = match.group(1).strip()
        slug = raw.replace(" ", "_")
        if slug:
            slugs.add(slug)
    return sorted(slugs)


def _normalize_tags(raw_tags):
    """Ensure tags is always a list of strings."""
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        return [raw_tags]
    return [str(t) for t in raw_tags]


def parse_page(filepath: str, project_root: str) -> dict:
    """Parse a single markdown file and return a metadata dict."""
    with open(filepath, "r", encoding="utf-8") as f:
        post = frontmatter.load(f)

    meta = post.metadata
    body = post.content

    # sources_count: frontmatter "sources: N"
    sources_count = None
    if "sources" in meta:
        try:
            sources_count = int(meta["sources"])
        except (ValueError, TypeError):
            pass

    # Serialize raw_frontmatter as JSON-compatible dict for JSONB storage
    raw_fm = {}
    for k, v in meta.items():
        try:
            json.dumps(v)
            raw_fm[k] = v
        except (TypeError, ValueError):
            raw_fm[k] = str(v)

    return {
        "slug": parse_slug(filepath, project_root),
        "relative_path": str(Path(filepath).relative_to(project_root)),
        "category": parse_category(filepath, project_root),
        "title": extract_title(body),
        "created": meta.get("created"),
        "updated": meta.get("updated"),
        "sources_count": sources_count,
        "raw_frontmatter": json.dumps(raw_fm),
        "tags": _normalize_tags(meta.get("tags")),
        "links": extract_wikilinks(body),
    }


# ─── DB write helpers ─────────────────────────────────────────────────────────

def upsert_page(cur, page: dict) -> int:
    """Upsert the pages row and return page_id."""
    cur.execute(
        """
        INSERT INTO pages
            (slug, relative_path, category, title, created, updated,
             sources_count, raw_frontmatter, synced_at)
        VALUES
            (%(slug)s, %(relative_path)s, %(category)s, %(title)s,
             %(created)s, %(updated)s, %(sources_count)s,
             %(raw_frontmatter)s::jsonb, NOW())
        ON CONFLICT (slug) DO UPDATE SET
            relative_path   = EXCLUDED.relative_path,
            category        = EXCLUDED.category,
            title           = EXCLUDED.title,
            created         = EXCLUDED.created,
            updated         = EXCLUDED.updated,
            sources_count   = EXCLUDED.sources_count,
            raw_frontmatter = EXCLUDED.raw_frontmatter,
            synced_at       = NOW()
        RETURNING id
        """,
        page,
    )
    return cur.fetchone()[0]


def sync_tags(cur, page_id: int, tags: list) -> None:
    """Replace all page_tags rows for this page with the current tag list."""
    cur.execute("DELETE FROM page_tags WHERE page_id = %s", (page_id,))
    if tags:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO page_tags (page_id, tag) VALUES %s ON CONFLICT DO NOTHING",
            [(page_id, tag) for tag in tags],
        )


def sync_links(cur, slug: str, links: list) -> None:
    """Replace all page_links rows for this source_slug with the current link list."""
    cur.execute("DELETE FROM page_links WHERE source_slug = %s", (slug,))
    if links:
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO page_links (source_slug, target_slug) VALUES %s ON CONFLICT DO NOTHING",
            [(slug, target) for target in links],
        )


# ─── Disk walk ───────────────────────────────────────────────────────────────

def collect_md_files(project_root: str) -> list:
    """Return absolute paths of all .md files to sync.

    Includes:
      - All .md files under wiki/ (recursively)
      - log.md at the project root
    """
    root = Path(project_root)
    files = list((root / "wiki").rglob("*.md"))
    log_file = root / "log.md"
    if log_file.exists():
        files.append(log_file)
    return [str(f) for f in files]


def collect_disk_slugs(project_root: str) -> set:
    """Return the set of slugs currently on disk."""
    return {parse_slug(f, project_root) for f in collect_md_files(project_root)}


def purge_deleted_pages(cur, disk_slugs: set) -> int:
    """Delete pages rows whose slug is no longer on disk. Returns count deleted."""
    if not disk_slugs:
        # Safety: never delete everything if disk is empty
        return 0
    cur.execute(
        "DELETE FROM pages WHERE slug != ALL(%s) RETURNING id",
        (list(disk_slugs),),
    )
    return cur.rowcount


# ─── Main sync ───────────────────────────────────────────────────────────────

def sync_wiki(project_root: str, dry_run: bool = False) -> None:
    files = collect_md_files(project_root)
    disk_slugs = {parse_slug(f, project_root) for f in files}

    pages_parsed = []
    errors = []
    for filepath in files:
        try:
            pages_parsed.append(parse_page(filepath, project_root))
        except Exception as exc:
            errors.append((filepath, exc))

    if errors:
        print(f"  WARN: {len(errors)} file(s) failed to parse:")
        for filepath, exc in errors:
            print(f"    {filepath}: {exc}")

    if dry_run:
        print(f"[dry-run] Would sync {len(pages_parsed)} pages, skip DB writes.")
        for p in pages_parsed:
            print(f"  {p['category']:12s}  {p['slug']}  tags={p['tags']}  links={len(p['links'])}")
        return

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                total_tags = 0
                total_links = 0

                for page in pages_parsed:
                    page_id = upsert_page(cur, page)
                    sync_tags(cur, page_id, page["tags"])
                    sync_links(cur, page["slug"], page["links"])
                    total_tags += len(page["tags"])
                    total_links += len(page["links"])

                purged = purge_deleted_pages(cur, disk_slugs)

        print(
            f"Synced {len(pages_parsed)} pages, "
            f"{total_tags} tags, "
            f"{total_links} links, "
            f"{purged} stale rows purged."
        )
    finally:
        conn.close()


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    if "--dry-run" in args:
        args.remove("--dry-run")

    wiki_dir = None
    if "--wiki-dir" in args:
        idx = args.index("--wiki-dir")
        try:
            wiki_dir = args[idx + 1]
        except IndexError:
            raise SystemExit("ERROR: --wiki-dir requires a path argument")

    project_root = wiki_dir or str(Path(__file__).parent.resolve())

    if not Path(project_root, "wiki").is_dir():
        raise SystemExit(
            f"ERROR: No 'wiki/' directory found in {project_root}\n"
            "Run from the project root, or pass --wiki-dir PATH."
        )

    sync_wiki(project_root, dry_run=dry_run)


if __name__ == "__main__":
    main()
