# Implementation Plan: LLM Wiki Core Brain

This document outlines the detailed plan to implement the LLM Wiki "Core Brain" system as described in the requirements. The system will act as an intelligent, incremental knowledge base that stores, updates, queries, and visualizes data using LLMs and Obsidian.

## 1. Architecture & Directory Structure

The system is organized into three main layers, residing in a local file system for compatibility with Obsidian.

```text
llm-wiki/
├── raw/                # Source of truth: immutable raw files, articles, images
│   ├── assets/         # Downloaded images and media
│   └── documents/      # Original text, PDFs, etc.
├── wiki/               # The LLM-maintained knowledge base
│   ├── index.md        # Catalog of all pages, grouped by category
│   ├── entities/       # Markdown files about specific people, places, things
│   ├── concepts/       # Markdown files about ideas, theories, events
│   └── synthesis/      # Markdown files synthesizing multiple sources
├── log.md              # Append-only chronological log of all operations
├── AGENTS.md           # The Schema: Instructions for the LLM Agent
└── brain.py            # (Optional) CLI tool to orchestrate LLM actions programmatically
```

## 2. The Core Brain: Schema (`AGENTS.md`)

The "core brain" relies heavily on how the LLM is instructed to manage the wiki. We will create an `AGENTS.md` (or equivalent schema file) that strictly defines the LLM's role.

### Agent Directives:
*   **Immutable Raw Data:** Never modify files in `raw/`. Only read from them.
*   **Wiki Ownership:** Completely manage the `wiki/` directory. Ensure pages use Markdown and Obsidian-compatible wikilinks (`[[Page Name]]`).
*   **Frontmatter:** Add YAML frontmatter to every wiki page (tags, creation date, last updated, source counts) for Obsidian Dataview compatibility.
*   **Graph Linking:** Always consider how a new piece of information connects to existing pages. Use aggressive cross-referencing to enrich the Obsidian graph view.

## 3. Workflows (Implementation Details)

We will define three main operations. These can be executed by prompting an LLM Agent (like Claude Code or Codex) manually, or by implementing a wrapper CLI (`brain.py`).

### A. Ingestion Workflow (`store / update any data`)
When a new file is added to `raw/`:
1.  **Read:** The LLM reads the new source document.
2.  **Extract & Summarize:** Create a summary page in the wiki (e.g., `wiki/sources/Source_Name.md`).
3.  **Update Entities & Concepts:** Scan the existing `wiki/` pages. If the new source mentions existing entities/concepts, update those markdown files with the new information. Reconcile contradictions.
4.  **Create New Pages:** If significant new entities/concepts appear, create new `[[Page Name]]` files for them.
5.  **Index Update:** Add links to any new pages in `wiki/index.md`.
6.  **Log:** Append `## [YYYY-MM-DD] ingest | File Name` to `log.md`.

### B. Query Workflow (`query data`)
When the user asks a question:
1.  **Index Lookup:** The LLM first reads `wiki/index.md` to identify relevant pages.
2.  **Read Pages:** The LLM reads the identified markdown files.
3.  **Synthesize:** The LLM generates an answer.
4.  **Capture Value:** If the answer creates a valuable synthesis, comparison, or insight, the LLM creates a *new* page in `wiki/synthesis/` and links it in the index.

### C. Lint Workflow (Maintenance)
Periodically or on command:
1.  The LLM scans the `wiki/` directory.
2.  Fixes broken `[[links]]`.
3.  Flags contradictions or stale claims.
4.  Identifies "orphan" pages (pages with no inbound links) and tries to connect them.
5.  Appends `## [YYYY-MM-DD] lint | Summary of changes` to `log.md`.

## 4. Technology Stack & Integration

*   **Storage / Editor:** Obsidian (local markdown files, graph view, wikilinks, Dataview plugin).
*   **LLM Agent:** Claude Code, OpenAI Codex, or a custom Python script (`brain.py`) utilizing LLM APIs (e.g., Anthropic API, OpenAI API).
*   **Search (Scaling Phase):** When `index.md` becomes too large, integrate `qmd` or a local vector database (like ChromaDB or FAISS) for semantic search over the wiki directory.

## 5. Execution Steps for Phase 1

1.  Initialize the Git repository.
2.  Create the directory skeleton (`raw/`, `wiki/`, etc.).
3.  Write the complete `AGENTS.md` file detailing the prompt schema.
4.  Create template files for `wiki/index.md` and `log.md`.
5.  (Optional) Write a skeleton `brain.py` CLI script to demonstrate programmatic triggering of workflows.
