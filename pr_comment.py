"""Sticky PR comment structure, approval parsing, and rendering helpers.

This module is called from cli.py preview-pr and publish-merged to keep a
single updatable PR comment containing concise SQL change summaries and status.
"""

from dataclasses import dataclass
from typing import List, Optional


COMMENT_MARKER = "<!-- sql-confluence-bot:pr-doc-preview -->"
APPROVAL_TEXT = (
    "I have reviewed this generated summary and approve publishing to Confluence after merge."
)
NO_CHANGES_TEXT = "No documentation-impacting SQL logic changes are currently detected in this PR."


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


def build_pr_review_comment(
    entries: List[PRCommentEntry],
    approved: bool = False,
    no_changes_note: Optional[str] = None,
) -> str:
    checkbox = "x" if approved else " "
    lines = [
        COMMENT_MARKER,
        "# SQL Documentation Review",
        "",
        "Concise SQL change summary for this PR. Publication happens only after merge and approval.",
        "",
        f"- [{checkbox}] {APPROVAL_TEXT}",
        "",
    ]

    if no_changes_note:
        lines.extend([
            "Current status:",
            no_changes_note,
            "",
        ])

    for entry in entries:
        lines.extend(
            [
                f"## {entry.file_path}",
                "",
                entry.snippet,
                "",
                f"Confluence: {entry.confluence_url or 'Will be created after merge'}",
                f"Status: {entry.publish_status}",
                "",
            ]
        )

    return "\n".join(lines).strip()