import unittest

from pr_comment import (
    APPROVAL_TEXT,
    NO_CHANGES_TEXT,
    PRCommentEntry,
    build_pr_review_comment,
    build_summary_snippet,
    is_comment_approved,
)


class TestPRComment(unittest.TestCase):
    def test_build_summary_snippet_truncates_long_text(self):
        text = "word " * 200
        snippet = build_summary_snippet(text, max_length=60)
        self.assertLessEqual(len(snippet), 60)
        self.assertTrue(snippet.endswith("..."))

    def test_build_and_parse_approval_checkbox(self):
        entry = PRCommentEntry(
            file_path="models/example.sql",
            snippet="Builds a reporting dataset.",
            page_title="SQL Summary - models/example.sql",
            confluence_url=None,
        )
        unchecked = build_pr_review_comment([entry], approved=False)
        checked = build_pr_review_comment([entry], approved=True)

        self.assertIn(APPROVAL_TEXT, unchecked)
        self.assertFalse(is_comment_approved(unchecked))
        self.assertTrue(is_comment_approved(checked))

    def test_build_comment_with_no_change_note(self):
        comment = build_pr_review_comment([], approved=False, no_changes_note=NO_CHANGES_TEXT)
        self.assertIn("Current status:", comment)
        self.assertIn(NO_CHANGES_TEXT, comment)


if __name__ == "__main__":
    unittest.main()