import unittest

from sql_change_detector import (
    _extract_in_clause_values,
    _format_in_value_change,
    detect_sql_logic_changes,
    extract_filters,
    render_delta_snippet,
)


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

    def test_extract_in_clause_values(self):
        filter_text = "cp.country_code in('us','in','pk')"
        values, column = _extract_in_clause_values(filter_text)
        self.assertEqual(sorted(values), ['in', 'pk', 'us'])
        self.assertEqual(column.lower(), 'cp.country_code')

    def test_format_in_value_change(self):
        description = _format_in_value_change(['us', 'in', 'pk'], ['ca', 'gb'], 'country_code')
        self.assertIn("country_code", description)
        self.assertIn("US, IN, PK", description)
        self.assertIn("CA, GB", description)
        self.assertIn("now only CA, GB records are included", description)

    def test_render_snippet_concise_for_in_clause_change(self):
        old_sql = "SELECT * FROM customers WHERE country_code IN ('US', 'IN', 'PK')"
        new_sql = "SELECT * FROM customers WHERE country_code IN ('CA', 'GB')"
        delta = detect_sql_logic_changes(old_sql, new_sql)
        snippet = render_delta_snippet(delta)
        self.assertIn("country_code", snippet.lower())
        self.assertIn("CA, GB", snippet)
        self.assertNotIn("Added:", snippet)
        self.assertNotIn("Removed:", snippet)

    def test_extract_filters_splits_top_level_conditions(self):
        sql = "SELECT * FROM orders WHERE status IN ('D','P') AND country_code IN ('CA','PK') AND quantity >= 1"
        filters = extract_filters(sql)
        self.assertEqual(len(filters), 3)
        self.assertIn("status IN ('D','P')", filters)
        self.assertIn("country_code IN ('CA','PK')", filters)

    def test_render_snippet_stays_concise_for_large_query(self):
        old_sql = """
        WITH recent_orders AS (
            SELECT * FROM sales.orders o
            WHERE o.order_date >= DATE '2026-01-01' AND o.order_date < DATE '2027-01-01' AND o.total_amount > 100
        ), customer_profile AS (
            SELECT c.customer_id, c.country_code FROM crm.customers c WHERE c.is_active = 1
        )
        SELECT ro.order_id, cp.country_code
        FROM recent_orders ro
        INNER JOIN customer_profile cp ON ro.customer_id = cp.customer_id
        WHERE ro.status_code IN ('D','P') AND cp.country_code IN ('CA','PK') AND ro.order_id > 0
        """
        new_sql = old_sql.replace("cp.country_code IN ('CA','PK')", "cp.country_code IN ('GB')")

        delta = detect_sql_logic_changes(old_sql, new_sql)
        snippet = render_delta_snippet(delta)

        self.assertIn("country_code filter changed", snippet.lower())
        self.assertIn("CA, PK", snippet)
        self.assertIn("GB", snippet)
        self.assertNotIn("recent_orders", snippet.lower())
        self.assertNotIn("Added:", snippet)
        self.assertLess(len(snippet), 220)


if __name__ == "__main__":
    unittest.main()
