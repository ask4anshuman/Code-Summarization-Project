import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli import preview_pr
from config import RepositoryConfig
from pr_comment import NO_CHANGES_TEXT


class FakeGithubManager:
    def __init__(self):
        self.upsert_calls = []

    def find_pr_comment(self, _pr_number, _marker):
        return {
            "id": 99,
            "body": "<!-- sql-confluence-bot:pr-doc-preview -->\n- [x] I have reviewed this generated summary and approve publishing to Confluence after merge.",
        }

    def upsert_pr_comment(self, pr_number, marker, body):
        self.upsert_calls.append({"pr_number": pr_number, "marker": marker, "body": body})
        return {"id": 99, "body": body}


class TestCLIPreviewPR(unittest.TestCase):
    def test_preview_pr_preserves_approval_when_no_changes(self):
        fake_github = FakeGithubManager()
        repo_config = RepositoryConfig(
            name="test",
            repo_root=".",
            github_repo="owner/repo",
            github_base_url="https://api.github.com",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "sql_confluence.yml"
            config_path.write_text("repository: {}\n", encoding="utf-8")

            with (
                patch("cli.GithubManager.from_env", return_value=fake_github),
                patch("cli._build_sql_change_entries", return_value=[]),
            ):
                preview_pr(repo_config, config_path, pr_number=123, sql_path=None)

        self.assertEqual(len(fake_github.upsert_calls), 1)
        updated_body = fake_github.upsert_calls[0]["body"]
        self.assertIn("- [x] I have reviewed this generated summary", updated_body)
        self.assertIn(NO_CHANGES_TEXT, updated_body)


if __name__ == "__main__":
    unittest.main()
