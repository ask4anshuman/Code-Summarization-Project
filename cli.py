import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from llm_service import LLMService
from confluence_manager import ConfluenceManager
from config import AppConfig, RepositoryConfig, get_repository_config, load_config
from github_manager import GithubManager
from git_tracker import list_changed_sql_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SQL to Confluence summarizer CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="sql_confluence.yml",
        help="Path to the YAML configuration file.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repository config name when multiple repositories are defined.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_preview = subparsers.add_parser("preview", help="Preview proposed SQL summary updates.")
    parser_preview.add_argument(
        "--sql-path",
        default=None,
        help="Optional path to a single SQL file to preview.",
    )

    parser_describe = subparsers.add_parser("describe", help="Describe SQL using raw SQL and an LLM.")
    parser_describe.add_argument(
        "--sql-path",
        default=None,
        help="Optional path to a single SQL file to describe.",
    )

    parser_diff = subparsers.add_parser("diff", help="List SQL files changed by Git.")
    parser_diff.add_argument(
        "--diff-range",
        default=None,
        help="Git diff range to compare, e.g. HEAD~1..HEAD.",
    )

    parser_publish = subparsers.add_parser("publish", help="Publish approved summary updates to Confluence.")
    parser_publish.add_argument(
        "--sql-path",
        default=None,
        help="Optional path to a single SQL file to publish.",
    )
    parser_publish.add_argument(
        "--pr-number",
        type=int,
        default=None,
        help="Optional GitHub pull request number. When provided, SQL files are loaded from the PR.",
    )
    parser_publish.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation and publish immediately.",
    )

    return parser


def resolve_repo_root(repo_config: RepositoryConfig, config_path: Path) -> Path:
    return repo_config.resolve_repo_root(config_path.parent)


def create_summarizer(repo_config: RepositoryConfig) -> LLMService:
    return LLMService(
        provider=repo_config.llm_provider,
        model=repo_config.llm_model,
        api_key=repo_config.get_llm_api_key(),
        api_base_url=repo_config.llm_api_base_url,
    )


def create_confluence_manager(repo_config: RepositoryConfig) -> ConfluenceManager:
    return ConfluenceManager(
        base_url=repo_config.confluence_base_url,
        space=repo_config.confluence_space,
        parent_page_id=repo_config.confluence_parent_page_id,
        cache_path=repo_config.cache_path,
        managed_section_start=repo_config.managed_section_start,
        managed_section_end=repo_config.managed_section_end,
    )


def resolve_sql_files(repo_root: Path, sql_path: Optional[str], diff_range: Optional[str]) -> List[Path]:
    if sql_path:
        sql_file = Path(sql_path)
        if not sql_file.is_absolute():
            sql_file = repo_root / sql_file
        if not sql_file.exists():
            raise FileNotFoundError(f"SQL file not found: {sql_file}")
        return [sql_file]

    return list_changed_sql_files(repo_root, diff_range)


def resolve_pr_sql_files(
    repo_config: RepositoryConfig,
    repo_root: Path,
    pr_number: int,
    sql_path: Optional[str],
) -> Tuple[List[Path], Dict[Path, str], GithubManager]:
    if not repo_config.github_repo:
        raise ValueError("github_repo must be set in config to use --pr-number.")

    github = GithubManager.from_env(repo_config.github_repo, repo_config.github_base_url)
    sql_contents = github.get_pr_sql_file_contents(pr_number)

    if sql_path:
        requested = sql_path.replace("\\", "/")
        if requested not in sql_contents:
            raise ValueError(
                f"SQL path '{sql_path}' not found in PR #{pr_number}. "
                "Use a repository-relative path from the PR file list."
            )
        sql_contents = {requested: sql_contents[requested]}

    sql_files = [repo_root / Path(path) for path in sql_contents.keys()]
    file_content_map = {repo_root / Path(path): content for path, content in sql_contents.items()}
    return sql_files, file_content_map, github


def format_confluence_url(page: Dict[str, str], fallback_base: str) -> str:
    links = page.get("_links", {}) if isinstance(page, dict) else {}
    webui = links.get("webui", "")
    base = links.get("base", fallback_base.rstrip("/"))
    if webui.startswith("http://") or webui.startswith("https://"):
        return webui
    if webui:
        return f"{base.rstrip('/')}/{webui.lstrip('/')}"
    return fallback_base


def build_pr_comment(page_urls: List[str]) -> str:
    lines = ["Confluence documentation has been updated for this PR.", ""]
    for url in page_urls:
        lines.append(f"- {url}")
    return "\n".join(lines)


def preview(repo_config: RepositoryConfig, config_path: Path, sql_path: Optional[str]) -> None:
    print("=== SQL Confluence Summarizer Preview ===")
    repo_root = resolve_repo_root(repo_config, config_path)
    sql_files = resolve_sql_files(repo_root, sql_path, repo_config.git_diff_range)
    if not sql_files:
        print("No SQL files found for preview.")
        return

    summarizer = create_summarizer(repo_config)
    for sql_file in sql_files:
        sql_text = sql_file.read_text(encoding="utf-8")
        summary_text = summarizer.summarize_sql(sql_text, sql_file)
        print(f"\n--- {sql_file.relative_to(repo_root)} ---")
        print(summary_text)


def describe(repo_config: RepositoryConfig, config_path: Path, sql_path: Optional[str]) -> None:
    print("=== SQL LLM Description ===")
    repo_root = resolve_repo_root(repo_config, config_path)
    sql_files = resolve_sql_files(repo_root, sql_path, repo_config.git_diff_range)
    if not sql_files:
        print("No SQL files found to describe.")
        return

    summarizer = create_summarizer(repo_config)
    for sql_file in sql_files:
        sql_text = sql_file.read_text(encoding="utf-8")
        description = summarizer.describe_sql(sql_text, sql_file)
        print(f"\n--- {sql_file.relative_to(repo_root)} ---")
        print(description)


def diff(repo_config: RepositoryConfig, config_path: Path, diff_range: Optional[str]) -> None:
    print("=== SQL Confluence Summarizer Diff ===")
    repo_root = resolve_repo_root(repo_config, config_path)
    sql_files = list_changed_sql_files(repo_root, diff_range or repo_config.git_diff_range)
    if not sql_files:
        print("No changed SQL files found.")
        return

    for file_path in sql_files:
        print(file_path.relative_to(repo_root))


def publish(
    repo_config: RepositoryConfig,
    config_path: Path,
    skip_confirm: bool,
    sql_path: Optional[str] = None,
    pr_number: Optional[int] = None,
) -> None:
    print("=== SQL Confluence Summarizer Publish ===")
    repo_root = resolve_repo_root(repo_config, config_path)
    github = None
    sql_file_contents: Dict[Path, str] = {}

    if pr_number is not None:
        sql_files, sql_file_contents, github = resolve_pr_sql_files(
            repo_config,
            repo_root,
            pr_number,
            sql_path,
        )
    else:
        sql_files = resolve_sql_files(repo_root, sql_path, repo_config.git_diff_range)

    if not sql_files:
        print("No SQL files found for publishing.")
        return

    if not skip_confirm:
        print("The following SQL files will be published to Confluence:")
        for sql_file in sql_files:
            print(f" - {sql_file.relative_to(repo_root)}")
        answer = input("Approve publishing these summaries? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Publish canceled.")
            return

    summarizer = create_summarizer(repo_config)
    manager = create_confluence_manager(repo_config)
    published_urls: List[str] = []
    for sql_file in sql_files:
        sql_text = sql_file_contents.get(sql_file)
        if sql_text is None:
            sql_text = sql_file.read_text(encoding="utf-8")
        summary_text = summarizer.summarize_sql(sql_text, sql_file)
        page = manager.publish_page(sql_file, repo_root, summary_text, repo_config.page_title_prefix)
        print(f"Published {sql_file.relative_to(repo_root)} -> page id {page['id']}")
        published_urls.append(format_confluence_url(page, manager.base_url))

    if pr_number is not None and github is not None and published_urls:
        comment = build_pr_comment(published_urls)
        github.create_pr_comment(pr_number, comment)
        print(f"Posted Confluence update comment to PR #{pr_number}.")


def load_and_select_repo(config_path: Path, repo_name: Optional[str]) -> RepositoryConfig:
    app_config: AppConfig = load_config(config_path)
    return get_repository_config(app_config, repo_name)


def main() -> None:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    config_path = Path(args.config)
    repo_config = load_and_select_repo(config_path, args.repo)

    if args.command == "preview":
        preview(repo_config, config_path, getattr(args, "sql_path", None))
    elif args.command == "diff":
        diff(repo_config, config_path, getattr(args, "diff_range", None))
    elif args.command == "publish":
        publish(
            repo_config,
            config_path,
            getattr(args, "yes", False),
            getattr(args, "sql_path", None),
            getattr(args, "pr_number", None),
        )
    elif args.command == "describe":
        describe(repo_config, config_path, getattr(args, "sql_path", None))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
