# SQL-to-Confluence Summarizer

Standalone Python tool to summarize SQL logic with an LLM, attach delta-only review snippets to PR comments, and publish managed summary updates to Confluence after merge.

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set any required values.
4. Create `sql_confluence.yml` in the repository root with your repository and Confluence settings.

## Configuration

Configuration source of truth:

- YAML (`sql_confluence.yml`): all non-secret settings
- Environment (`.env`): secrets only

The repository config uses these LLM keys:

- `llm_provider`: LLM service provider identifier, such as `openai` or `local`
- `llm_model`: the model name or identifier
- `llm_api_base_url`: required LLM API base URL
- `git_diff_range`: optional Git diff range to determine changed `.sql` files
- `github_repo`: optional GitHub repository in `owner/repo` format for PR integration
- `github_base_url`: GitHub API base URL, such as `https://api.github.com`

Secrets that must be provided via `.env`:

- `LLM_API_KEY`
- `CONFLUENCE_USERNAME`
- `CONFLUENCE_API_TOKEN`
- `SQ_GITHUB_TOKEN` (required for PR integration)

The `local` provider can be used for local fallback behavior without requiring an external API key.

## Commands

Run commands from the repository root:

```bash
python main.py --config sql_confluence.yml <command> [options]
```

### preview

Preview generated SQL summaries without publishing anything.

```bash
python main.py --config sql_confluence.yml preview
```

Optional single-file preview:

```bash
python main.py --config sql_confluence.yml preview --sql-path path/to/query.sql
```

### describe

Generate a detailed LLM description for SQL logic.

```bash
python main.py --config sql_confluence.yml describe --sql-path path/to/query.sql
```

### diff

List SQL files changed by Git:

```bash
python main.py --config sql_confluence.yml diff
```

Optional Git range:

```bash
python main.py --config sql_confluence.yml diff --diff-range HEAD~2..HEAD
```

### publish

Publish approved SQL summaries to Confluence. This command uses the same changed-file selection as `diff`.

```bash
python main.py --config sql_confluence.yml publish
```

Optional single-file publish:

```bash
python main.py --config sql_confluence.yml publish --sql-path path/to/query.sql
```

Skip interactive confirmation:

```bash
python main.py --config sql_confluence.yml publish --yes
```

### preview-pr

Generate a sticky PR comment with:

- a natural-language snippet per changed SQL file that only explains modified SQL logic
- the target Confluence page title
- the existing Confluence link when a page already exists
- a review checkbox that a human must check before merge publication

```bash
python main.py --config sql_confluence.yml preview-pr --pr-number 123
```

Behavior details:

- For modified SQL files, the snippet includes only logic deltas (filters, joins, CTEs, tables, output columns/transforms).
- Formatting-only changes are skipped from the sticky comment.
- The command never publishes to Confluence.

Optional single-file PR preview:

```bash
python main.py --config sql_confluence.yml preview-pr --pr-number 123 --sql-path path/to/query.sql
```

### publish-merged

Publish Confluence updates only after a PR is merged and the sticky PR review comment checkbox is checked.

```bash
python main.py --config sql_confluence.yml publish-merged --pr-number 123
```

Optional single-file merged publish:

```bash
python main.py --config sql_confluence.yml publish-merged --pr-number 123 --sql-path path/to/query.sql
```

PR integration requirements:

- Set `github_repo` in your YAML repository config
- Set `github_base_url` in your YAML repository config
- Set `SQ_GITHUB_TOKEN` in environment with permission to read PR files and read/write PR comments

### Automatic publish after merge (GitHub Actions)

This repository includes a workflow at `.github/workflows/sql-confluence-publish-on-merge.yml`.

- Trigger: pull request `closed`
- Guard: runs only when `merged == true`
- Action: executes `publish-merged` for that PR number

Required repository secrets for the workflow:

- `LLM_API_KEY`
- `CONFLUENCE_USERNAME`
- `CONFLUENCE_API_TOKEN`

If you prefer manual execution, CLI commands remain available.

## PR workflow

1. Run `preview-pr` on an open PR.
2. Review the generated sticky comment in GitHub (delta-only snippets).
3. A human checks the approval checkbox in that comment.
4. Merge the PR.
5. Publishing runs automatically via workflow using `publish-merged`.
6. Optional fallback: run `publish-merged` manually via CLI.

The tool intentionally does not publish to Confluence during `preview-pr`.

## Multi-repository support

If your config file defines more than one repository, specify the target with `--repo`:

```bash
python main.py --config sql_confluence.yml --repo my-repo preview
```

## Tests

Run the unit tests from the repository root:

```bash
python -m unittest discover -s tests
```
