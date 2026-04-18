import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv

from llm_service import LLMService
from confluence_manager import ConfluenceManager
from config import AppConfig, RepositoryConfig, get_repository_config, load_config
from github_manager import GithubManager
from git_tracker import list_changed_sql_files
from pr_comment import (
    COMMENT_MARKER,
    NO_CHANGES_TEXT,
    PRCommentEntry,
    build_pr_review_comment,
    is_comment_approved,
)
from sql_change_detector import detect_sql_logic_changes, render_delta_snippet


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

    parser_preview_pr = subparsers.add_parser(
        "preview-pr",
        help="Generate PR review comment with summary snippets and approval checkbox.",
    )
    parser_preview_pr.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="GitHub pull request number to preview.",
    )
    parser_preview_pr.add_argument(
        "--sql-path",
        default=None,
        help="Optional path to a single SQL file from the PR to preview.",
    )

    parser_publish = subparsers.add_parser("publish", help="Publish approved summary updates to Confluence.")
    parser_publish.add_argument(
        "--sql-path",
        default=None,
        help="Optional path to a single SQL file to publish.",
    )
    parser_publish.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive confirmation and publish immediately.",
    )

    parser_publish_merged = subparsers.add_parser(
        "publish-merged",
        help="Publish Confluence updates for a merged and approved PR.",
    )
    parser_publish_merged.add_argument(
        "--pr-number",
        type=int,
        required=True,
        help="GitHub pull request number to publish after merge.",
    )
    parser_publish_merged.add_argument(
        "--sql-path",
        default=None,
        help="Optional path to a single SQL file from the PR to publish.",
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
    ref: Optional[str] = None,
) -> Tuple[List[Path], Dict[Path, str], GithubManager]:
    if not repo_config.github_repo:
        raise ValueError("github_repo must be set in config to use --pr-number.")

    github = GithubManager.from_env(repo_config.github_repo, repo_config.github_base_url)
    sql_contents = github.get_pr_sql_file_contents(pr_number, ref=ref)

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


CONFLUENCE_LINK_MARKER = "-- [Doc] Confluence:"


def inject_confluence_link(sql_file: Path, confluence_url: str, content: Optional[str] = None) -> bool:
    """Inject or update the Confluence documentation link as a SQL comment at the top of the file.
    Accepts optional pre-loaded content to avoid disk reads (e.g. for new files not yet on disk).
    Returns True if the file was written/modified."""
    if content is None:
        content = sql_file.read_text(encoding="utf-8")

    new_comment = f"{CONFLUENCE_LINK_MARKER} {confluence_url}"

    if CONFLUENCE_LINK_MARKER in content:
        updated = re.sub(
            r"-- \[Doc\] Confluence:.*",
            new_comment,
            content,
        )
        if updated == content:
            return False
        sql_file.parent.mkdir(parents=True, exist_ok=True)
        sql_file.write_text(updated, encoding="utf-8")
        return True

    sql_file.parent.mkdir(parents=True, exist_ok=True)
    sql_file.write_text(f"{new_comment}\n{content}", encoding="utf-8")
    return True


def format_confluence_url(page: Dict[str, str], fallback_base: str) -> str:
    links = page.get("_links", {}) if isinstance(page, dict) else {}
    webui = links.get("webui", "")
    base = links.get("base", fallback_base.rstrip("/"))
    if webui.startswith("http://") or webui.startswith("https://"):
        return webui
    if webui:
        return f"{base.rstrip('/')}/{webui.lstrip('/')}"
    return fallback_base


def _build_sql_change_entries(
    repo_config: RepositoryConfig,
    repo_root: Path,
    pr_number: int,
    github: GithubManager,
    sql_path: Optional[str] = None,
) -> List[PRCommentEntry]:
    refs = github.get_pr_refs(pr_number)
    changes = github.list_pr_sql_file_changes(pr_number)
    if sql_path:
        requested = sql_path.replace("\\", "/")
        changes = [
            item
            for item in changes
            if item.get("filename") == requested or item.get("previous_filename") == requested
        ]

    manager = create_confluence_manager(repo_config)
    entries: List[PRCommentEntry] = []
    for item in changes:
        status = item.get("status", "modified")
        filename = item.get("filename", "")
        previous_filename = item.get("previous_filename", "")
        old_path = previous_filename or filename
        new_path = filename or previous_filename
        if not new_path:
            continue

        old_sql = None if status == "added" else github.get_file_content_if_exists(old_path, refs["base"])
        new_sql = None if status == "removed" else github.get_file_content_if_exists(new_path, refs["head"])
        delta = detect_sql_logic_changes(old_sql, new_sql, change_kind=status)
        if status == "modified" and not delta.has_logic_changes():
            continue

        repo_relative = Path(new_path)
        page_file_path = repo_root / repo_relative
        page_title = manager.get_page_title(page_file_path, repo_root, repo_config.page_title_prefix)
        confluence_url = manager.get_existing_page_url(page_file_path, repo_root, repo_config.page_title_prefix)
        entries.append(
            PRCommentEntry(
                file_path=str(repo_relative).replace("\\", "/"),
                snippet=render_delta_snippet(delta),
                page_title=page_title,
                confluence_url=confluence_url,
            )
        )
    return entries


def preview_pr(
    repo_config: RepositoryConfig,
    config_path: Path,
    pr_number: int,
    sql_path: Optional[str],
) -> None:
    print("=== SQL Confluence Summarizer PR Preview ===")
    repo_root = resolve_repo_root(repo_config, config_path)
    if not repo_config.github_repo:
        raise ValueError("github_repo must be set in config to use preview-pr.")
    github = GithubManager.from_env(repo_config.github_repo, repo_config.github_base_url)
    existing_comment = github.find_pr_comment(pr_number, COMMENT_MARKER)
    was_approved = False
    if existing_comment is not None:
        comment_body = str(existing_comment.get("body", ""))
        was_approved = is_comment_approved(comment_body)

    entries = _build_sql_change_entries(repo_config, repo_root, pr_number, github, sql_path)
    if not entries:
        comment = build_pr_review_comment([], approved=was_approved, no_changes_note=NO_CHANGES_TEXT)
        github.upsert_pr_comment(pr_number, COMMENT_MARKER, comment)
        print("No documentation-impacting SQL logic changes found in the PR. Updated sticky comment status.")
        return

    comment = build_pr_review_comment(entries, approved=was_approved)
    github.upsert_pr_comment(pr_number, COMMENT_MARKER, comment)
    print(f"Updated PR #{pr_number} review comment for {len(entries)} SQL file(s) with delta-only snippets.")


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
) -> None:
    print("=== SQL Confluence Summarizer Publish ===")
    repo_root = resolve_repo_root(repo_config, config_path)
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
    for sql_file in sql_files:
        sql_text = sql_file.read_text(encoding="utf-8")
        summary_text = summarizer.summarize_sql(sql_text, sql_file)
        page = manager.publish_page(sql_file, repo_root, summary_text, repo_config.page_title_prefix)
        print(f"Published {sql_file.relative_to(repo_root)} -> page id {page['id']}")


def publish_merged(
    repo_config: RepositoryConfig,
    config_path: Path,
    pr_number: int,
    sql_path: Optional[str],
) -> None:
    print("=== SQL Confluence Summarizer Publish Merged PR ===")
    repo_root = resolve_repo_root(repo_config, config_path)
    if not repo_config.github_repo:
        raise ValueError("github_repo must be set in config to publish merged PRs.")

    github = GithubManager.from_env(repo_config.github_repo, repo_config.github_base_url)
    pr_payload = github.get_pr(pr_number)
    if not pr_payload.get("merged"):
        raise ValueError(f"PR #{pr_number} is not merged. Confluence publish is merge-only.")

    existing_comment = github.find_pr_comment(pr_number, COMMENT_MARKER)
    if existing_comment is None:
        raise ValueError(f"No approval comment found on PR #{pr_number}. Run preview-pr first.")

    comment_body = str(existing_comment.get("body", ""))
    if not is_comment_approved(comment_body):
        raise ValueError(
            f"PR #{pr_number} has not been approved in the sticky review comment. "
            "Check the checkbox before publishing."
        )

    merge_ref = pr_payload.get("merge_commit_sha")
    if not merge_ref:
        raise ValueError(f"PR #{pr_number} does not expose a merge_commit_sha.")

    sql_files, sql_file_contents, _ = resolve_pr_sql_files(
        repo_config,
        repo_root,
        pr_number,
        sql_path,
        ref=str(merge_ref),
    )
    if not sql_files:
        print("No SQL files found for merged publish.")
        return

    summarizer = create_summarizer(repo_config)
    manager = create_confluence_manager(repo_config)
    change_entries = _build_sql_change_entries(repo_config, repo_root, pr_number, github, sql_path)
    change_entry_map = {entry.file_path: entry for entry in change_entries}

    published_entries: List[PRCommentEntry] = []
    for sql_file in sql_files:
        sql_text = sql_file_contents[sql_file]
        summary_text = summarizer.summarize_sql(sql_text, sql_file)
        page = manager.publish_page(sql_file, repo_root, summary_text, repo_config.page_title_prefix)
        page_url = format_confluence_url(page, manager.base_url)
        print(f"Published {sql_file.relative_to(repo_root)} -> page id {page['id']}")
        if inject_confluence_link(sql_file, page_url, content=sql_text):
            print(f"  -> Injected Confluence link into {sql_file.name}")
        rel_file = str(sql_file.relative_to(repo_root)).replace("\\", "/")
        change_entry = change_entry_map.get(rel_file)
        snippet = change_entry.snippet if change_entry else "Published SQL documentation update after merge."
        published_entries.append(
            PRCommentEntry(
                file_path=rel_file,
                snippet=snippet,
                page_title=manager.get_page_title(sql_file, repo_root, repo_config.page_title_prefix),
                confluence_url=page_url,
                publish_status="Published after merge",
            )
        )

    updated_comment = build_pr_review_comment(published_entries, approved=True)
    github.upsert_pr_comment(pr_number, COMMENT_MARKER, updated_comment)
    print(f"Updated PR #{pr_number} review comment with final Confluence links.")


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
    elif args.command == "preview-pr":
        preview_pr(
            repo_config,
            config_path,
            getattr(args, "pr_number"),
            getattr(args, "sql_path", None),
        )
    elif args.command == "diff":
        diff(repo_config, config_path, getattr(args, "diff_range", None))
    elif args.command == "publish":
        publish(
            repo_config,
            config_path,
            getattr(args, "yes", False),
            getattr(args, "sql_path", None),
        )
    elif args.command == "publish-merged":
        publish_merged(
            repo_config,
            config_path,
            getattr(args, "pr_number"),
            getattr(args, "sql_path", None),
        )
    elif args.command == "describe":
        describe(repo_config, config_path, getattr(args, "sql_path", None))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
