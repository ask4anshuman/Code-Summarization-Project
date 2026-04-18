import unittest

from github_manager import GithubManager


class TestGithubManager(unittest.TestCase):
    def test_find_pr_comment_returns_latest_marker_comment(self):
        manager = GithubManager(repo="owner/repo", token="token", api_base_url="https://api.github.com")

        def fake_comments(_pr_number):
            return [
                {
                    "id": 10,
                    "created_at": "2026-04-18T10:00:00Z",
                    "body": "random comment",
                },
                {
                    "id": 12,
                    "created_at": "2026-04-18T10:01:00Z",
                    "body": "<!-- sql-confluence-bot:pr-doc-preview --> old sticky",
                },
                {
                    "id": 15,
                    "created_at": "2026-04-18T10:05:00Z",
                    "body": "<!-- sql-confluence-bot:pr-doc-preview --> latest sticky",
                },
            ]

        manager.list_issue_comments = fake_comments  # type: ignore[method-assign]
        found = manager.find_pr_comment(123, "<!-- sql-confluence-bot:pr-doc-preview -->")

        self.assertIsNotNone(found)
        self.assertEqual(found["id"], 15)


if __name__ == "__main__":
    unittest.main()
