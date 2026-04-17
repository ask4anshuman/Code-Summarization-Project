from dataclasses import dataclass
from typing import List, Optional


COMMENT_MARKER = "<!-- sql-confluence-bot:pr-doc-preview -->"
APPROVAL_TEXT = (
    "I have reviewed this generated summary and approve publishing to Confluence after merge."
)


@dataclass
class PRCommentEntry:
    file_path: str
    snippet: str
    page_title: str
    confluence_url: Optional[str] = None
    publish_status: str = "Pending merge"


def build_summary_snippet(summary_text: str, max_length: int = 400) -> str:
    normalized = " ".join(summary_text.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3].rstrip()}..."


def is_comment_approved(comment_body: str) -> bool:
    normalized = comment_body.lower()
    return f"- [x] {APPROVAL_TEXT}".lower() in normalized


def build_pr_review_comment(entries: List[PRCommentEntry], approved: bool = False) -> str:
    checkbox = "x" if approved else " "
    lines = [
        COMMENT_MARKER,
        "# SQL Documentation Review",
        "",
        "Review the generated SQL summary snippets below. Confluence publication will happen only after the PR is merged and this checkbox is checked.",
        "",
        f"- [{checkbox}] {APPROVAL_TEXT}",
        "",
    ]

    for entry in entries:
        lines.extend(
            [
                f"## {entry.file_path}",
                "",
                "Summary snippet:",
                entry.snippet,
                "",
                f"Confluence page title: `{entry.page_title}`",
                f"Confluence link: {entry.confluence_url or 'Will be created after merge'}",
                f"Publish status: {entry.publish_status}",
                "",
            ]
        )

    return "\n".join(lines).strip()