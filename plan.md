# SQL-to-Confluence Summarizer

## Overview

This project is a standalone Python application that scans SQL files in a repository, extracts their logic, generates human-readable summaries, and publishes one Confluence page per SQL file. The application is repository-agnostic and can be configured for any target repository and Confluence location.

The system tracks Git-driven SQL changes, attaches change-only snippets to sticky PR comments for manual review, and publishes updates only after merge when the PR review comment has been approved.

## Goals

- Parse SQL code logic and extract:
  - tables and sources
  - CTEs and subqueries
  - join clauses and join conditions
  - filter conditions
  - select columns and column translations
- Generate a human-readable summary using a hosted LLM.
- Map each SQL file to a dedicated Confluence page.
- Publish or update only the managed summary section, preserving manual edits elsewhere.
- Detect SQL changes via Git and propose only relevant updates.
- Require explicit approval in a sticky PR comment checkbox before sending updates to Confluence after merge.
- Support automatic post-merge publication via GitHub Actions while retaining manual CLI publish commands.

## Components

1. `cli.py`
   - Command-line interface for preview, diff, and publish workflows.
   - Config loading, repository selection, and manual confirmation.

2. `config.py`
   - YAML-based configuration loader.
   - Repository and Confluence target configuration.
   - Environment variable overrides for API keys.

3. `llm_service.py`
   - Prompt builder for a hosted LLM service.
   - Summary generation and diffable outline creation.

4. `confluence_manager.py`
   - Confluence REST integration.
   - Page creation and managed section updates.
   - Local page cache mapping SQL files to Confluence page IDs.

5. `github_manager.py`
   - GitHub PR file retrieval.
   - Sticky PR comment create/update behavior.
   - Merge-state lookup for merge-only publishing.

6. `git_tracker.py`
   - Git diff detection for changed SQL files.
   - Change-aware summary update gating.

7. `pr_comment.py`
   - Sticky PR review comment rendering.
   - Approval checkbox parsing.

8. `sql_change_detector.py`
   - SQL logic delta extraction between previous and current revisions.
   - Delta-only snippet rendering for PR comments.

9. `tests/`
   - Unit tests for parser, config, Confluence manager, and Git tracker.

## Completed work

- Created the project scaffolding and environment metadata:
  - `pyproject.toml`, `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, `main.py`, `__init__.py`
- Implemented configuration loading and validation in `config.py`.
- Implemented CLI tooling in `cli.py` with `preview`, `diff`, and `publish` commands.
- Built LLM summary generation in `llm_service.py`, including service provider support and local fallback.
- Implemented Confluence page management in `confluence_manager.py` with managed summary section merging.
- Implemented Git-based SQL change detection in `git_tracker.py`.
- Implemented PR review comment rendering and approval parsing in `pr_comment.py`.
- Extended GitHub integration to upsert sticky PR comments and inspect merge state.
- Added SQL change detection in `sql_change_detector.py` and switched PR comments to delta-only snippets.
- Added GitHub Actions workflow `.github/workflows/sql-confluence-publish-on-merge.yml` for automatic publish after merge.
- Refactored CLI to support `preview-pr` and `publish-merged` so Confluence publishing is merge-only for PR flows while preserving manual CLI publish.
- Added sample `sql_confluence.yml` repository config.
- Added unit tests under `tests/` and validated project dependencies.

## Phase 1 — Initial implementation

- Create project scaffolding.
- Implement `config.py` for config loading and validation.
- Implement `cli.py` skeleton with preview/diff/publish commands.
- Add sample config file path and default config values.

## Config schema

The application will support a YAML configuration file with either a single repository config or multiple repository entries.

Example:

```yaml
repositories:
  - name: example-repo
    repo_root: .
    sql_glob: "**/*.sql"
    confluence_base_url: "https://your-company.atlassian.net/wiki"
    confluence_space: "DATA"
    confluence_parent_page_id: "123456789"
    page_title_prefix: "SQL Summary - "
    llm_provider: "openai"
    llm_model: "gpt-4.1-mini"
    git_diff_range: "HEAD~1..HEAD"
    cache_path: ".sql_confluence_cache.yml"
```

## Next steps

- Finalize edge-case SQL parsing for multiple query files and dialect variance.
- Improve AI prompt quality for clearer Confluence documentation output.
- Add integration tests for Confluence page creation and update flows (mocked API behavior).
- Add integration tests for sticky PR comment update behavior and merged PR publishing.
- Add integration tests for PR file rename/remove behavior in delta generation.
- Add optional non-interactive automation flags and repository onboarding documentation.
