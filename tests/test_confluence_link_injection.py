import tempfile
import unittest
from pathlib import Path

from cli import CONFLUENCE_LINK_MARKER, inject_confluence_link, move_confluence_marker_to_line


class TestConfluenceLinkInjection(unittest.TestCase):
    def _write_sql(self, dir_path: str, content: str) -> Path:
        sql_file = Path(dir_path) / "query.sql"
        sql_file.write_text(content, encoding="utf-8")
        return sql_file

    def test_injects_link_at_top_of_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = self._write_sql(tmpdir, "SELECT * FROM orders;\n")
            changed = inject_confluence_link(sql_file, "https://confluence.example.com/pages/123")
            content = sql_file.read_text(encoding="utf-8")

        self.assertTrue(changed)
        first_line = content.splitlines()[0]
        self.assertTrue(first_line.startswith(CONFLUENCE_LINK_MARKER))
        self.assertIn("https://confluence.example.com/pages/123", first_line)
        self.assertIn("SELECT * FROM orders;", content)

    def test_injects_link_using_in_memory_content_no_disk_read(self):
        """New file case: file does not exist on disk yet; content passed directly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = Path(tmpdir) / "subdir" / "new_query.sql"
            # File does NOT exist on disk — simulate new PR file loaded from GitHub API
            in_memory_content = "SELECT * FROM customers;\n"
            changed = inject_confluence_link(
                sql_file, "https://confluence.example.com/pages/999", content=in_memory_content
            )
            content = sql_file.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertTrue(content.startswith(CONFLUENCE_LINK_MARKER))
        self.assertIn("https://confluence.example.com/pages/999", content)
        self.assertIn("SELECT * FROM customers;", content)

    def test_updates_existing_link(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = self._write_sql(
                tmpdir,
                "-- [Doc] Confluence: https://old-link.com/pages/1\nSELECT * FROM orders;\n",
            )
            changed = inject_confluence_link(sql_file, "https://new-link.com/pages/99")
            content = sql_file.read_text(encoding="utf-8")

        self.assertTrue(changed)
        self.assertIn("https://new-link.com/pages/99", content)
        self.assertNotIn("https://old-link.com/pages/1", content)

    def test_no_change_when_link_identical(self):
        url = "https://confluence.example.com/pages/42"
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = self._write_sql(
                tmpdir,
                f"-- [Doc] Confluence: {url}\nSELECT 1;\n",
            )
            changed = inject_confluence_link(sql_file, url)

        self.assertFalse(changed)

    def test_each_file_gets_its_own_link(self):
        """Three different SQL files get three different Confluence links injected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            files_and_links = [
                ("customers.sql", "https://confluence.example.com/pages/101"),
                ("orders.sql", "https://confluence.example.com/pages/102"),
                ("products.sql", "https://confluence.example.com/pages/103"),
            ]
            for filename, url in files_and_links:
                sql_file = Path(tmpdir) / filename
                sql_file.write_text(f"SELECT * FROM {filename.replace('.sql', '')};\n", encoding="utf-8")
                inject_confluence_link(sql_file, url)

            for filename, url in files_and_links:
                content = (Path(tmpdir) / filename).read_text(encoding="utf-8")
                self.assertIn(url, content)
                self.assertIn(CONFLUENCE_LINK_MARKER, content)

    def test_move_marker_to_line_four(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = self._write_sql(
                tmpdir,
                "-- [Doc] Confluence: https://confluence.example.com/pages/1\nSELECT 1;\n",
            )
            changed = move_confluence_marker_to_line(sql_file, target_line_number=4)
            content = sql_file.read_text(encoding="utf-8")

        self.assertTrue(changed)
        lines = content.splitlines()
        self.assertGreaterEqual(len(lines), 4)
        self.assertTrue(lines[3].startswith(CONFLUENCE_LINK_MARKER))

    def test_move_marker_to_line_four_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sql_file = self._write_sql(
                tmpdir,
                "SELECT col1\nFROM tab\nWHERE x = 1\n-- [Doc] Confluence: https://confluence.example.com/pages/1\n",
            )
            changed = move_confluence_marker_to_line(sql_file, target_line_number=4)

        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
