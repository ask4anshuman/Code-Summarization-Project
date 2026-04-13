# SQL-to-Confluence Summarizer

Standalone Python tool to summarize SQL logic with an LLM and publish managed summary updates to Confluence.

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
- `GITHUB_TOKEN` (required for PR integration)

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

Optional PR-based publish from GitHub (no local SQL checkout needed):

```bash
python main.py --config sql_confluence.yml publish --pr-number 123 --yes
```

PR mode requirements:

- Set `github_repo` in your YAML repository config
- Set `github_base_url` in your YAML repository config
- Set `GITHUB_TOKEN` in environment (token must be able to read PR files and write PR comments)

Skip interactive confirmation:

```bash
python main.py --config sql_confluence.yml publish --yes
```

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
