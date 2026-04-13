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


if __name__ == "__main__":
    unittest.main()
