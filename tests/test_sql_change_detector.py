import unittest

from sql_change_detector import detect_sql_logic_changes, render_delta_snippet


class TestSQLChangeDetector(unittest.TestCase):
    def test_detects_filter_and_column_changes(self):
        old_sql = "SELECT order_id FROM orders WHERE status = 'open'"
        new_sql = "SELECT order_id, customer_id FROM orders WHERE status = 'open' AND amount > 100"

        delta = detect_sql_logic_changes(old_sql, new_sql)
        self.assertIn("amount>100", " ".join(delta.added_filters))
        self.assertIn("customer_id", " ".join(delta.added_columns).lower())
        self.assertTrue(delta.has_logic_changes())

    def test_no_logic_change_for_formatting_only(self):
        old_sql = "SELECT order_id FROM orders WHERE status='open'"
        new_sql = "\n  SELECT order_id\n  FROM orders\n  WHERE status = 'open'\n"

        delta = detect_sql_logic_changes(old_sql, new_sql)
        self.assertFalse(delta.has_logic_changes())

    def test_render_snippet_for_added_file(self):
        delta = detect_sql_logic_changes(None, "SELECT id FROM orders", change_kind="added")
        snippet = render_delta_snippet(delta)
        self.assertIn("New SQL file added", snippet)


if __name__ == "__main__":
    unittest.main()
