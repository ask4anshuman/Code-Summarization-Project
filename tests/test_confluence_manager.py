import unittest
from pathlib import Path

from confluence_manager import ConfluenceManager


class TestConfluenceManager(unittest.TestCase):
    def test_merge_managed_section_inserts_and_replaces(self):
        manager = ConfluenceManager(
            base_url="https://example.atlassian.net/wiki",
            space="DATA",
            parent_page_id="123",
            username="user",
            api_token="token",
            cache_path=".test_cache.yml",
        )
        original_content = "<p>Manual content</p>"
        summary_text = "This is the SQL summary."
        merged = manager.merge_managed_section(original_content, summary_text)
        self.assertIn(manager.managed_section_start, merged)
        self.assertIn(manager.managed_section_end, merged)
        self.assertIn("This is the SQL summary.", merged)

        updated_summary = "This is the updated SQL summary."
        replaced = manager.merge_managed_section(merged, updated_summary)
        self.assertIn(updated_summary, replaced)
        self.assertNotIn("This is the SQL summary.", replaced)

    def test_resolve_parent_page_id_uses_longest_prefix(self):
        manager = ConfluenceManager(
            base_url="https://example.atlassian.net/wiki",
            space="DATA",
            parent_page_id="1000",
            parent_page_map={
                "marts/": "2001",
                "marts/finance/": "2002",
                "staging/": "3001",
            },
            username="user",
            api_token="token",
            cache_path=".test_cache.yml",
        )

        repo_root = Path(".").resolve()
        sql_file = repo_root / "marts" / "finance" / "daily_report.sql"
        resolved = manager.resolve_parent_page_id(sql_file, repo_root)

        self.assertEqual(resolved, "2002")

    def test_resolve_parent_page_id_uses_default_when_no_match(self):
        manager = ConfluenceManager(
            base_url="https://example.atlassian.net/wiki",
            space="DATA",
            parent_page_id="1000",
            parent_page_map={"marts/": "2001"},
            username="user",
            api_token="token",
            cache_path=".test_cache.yml",
        )

        repo_root = Path(".").resolve()
        sql_file = repo_root / "sandbox" / "adhoc_query.sql"
        resolved = manager.resolve_parent_page_id(sql_file, repo_root)

        self.assertEqual(resolved, "1000")


if __name__ == "__main__":
    unittest.main()
