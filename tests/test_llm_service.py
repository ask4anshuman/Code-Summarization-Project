import unittest
from pathlib import Path

from llm_service import LLMService


class TestLLMService(unittest.TestCase):
    def test_summarize_sql_local_fallback(self):
        sql = "SELECT a, b FROM orders WHERE active = 1"
        service = LLMService(provider="local")
        text = service.summarize_sql(sql)

        self.assertIn("SQL Description", text)
        self.assertIn(sql, text)

    def test_describe_sql_includes_required_sections(self):
        sql = "SELECT a, b FROM orders WHERE active = 1"
        service = LLMService(provider="local")
        prompt = service._build_description_prompt(sql, Path("query.sql"))

        self.assertIn("number of tables used", prompt.lower())
        self.assertIn("cte", prompt.lower())
        self.assertIn("join types", prompt.lower())
        self.assertIn("filters applied in where", prompt.lower())
        self.assertIn("overall purpose", prompt.lower())
        self.assertIn("query.sql", prompt)
        self.assertIn(sql, prompt)


if __name__ == "__main__":
    unittest.main()
