import os
import tempfile
import unittest
from pathlib import Path

from config import load_config, get_repository_config


class TestConfig(unittest.TestCase):
    def test_load_single_repository(self):
        yaml_content = """
repositories:
  - name: test-repo
    repo_root: .
    sql_glob: "**/*.sql"
    confluence_base_url: "https://example.atlassian.net/wiki"
    confluence_space: "DATA"
    confluence_parent_page_id: "123"
    page_title_prefix: "SQL Summary - "
    llm_provider: "openai"
    llm_model: "gpt-4.1-mini"
    llm_api_base_url: "https://api.openai.com/v1/chat/completions"
    git_diff_range: "HEAD~1..HEAD"
    cache_path: ".sql_confluence_cache.yml"
"""
        with tempfile.NamedTemporaryFile("w+", suffix=".yml", delete=False) as config_file:
            config_file.write(yaml_content)
            config_path = Path(config_file.name)

        os.environ["LLM_API_KEY"] = "test-api-key"
        app_config = load_config(config_path)
        self.assertEqual(len(app_config.repositories), 1)
        repo_config = get_repository_config(app_config, "test-repo")
        self.assertEqual(repo_config.name, "test-repo")
        self.assertEqual(repo_config.confluence_space, "DATA")
        self.assertEqual(repo_config.git_diff_range, "HEAD~1..HEAD")

        def test_load_parent_page_map(self):
                yaml_content = """
repositories:
    - name: test-repo
        repo_root: .
        sql_glob: "**/*.sql"
        confluence_base_url: "https://example.atlassian.net/wiki"
        confluence_space: "DATA"
        confluence_parent_page_id: "123"
        confluence_parent_page_map:
            marts/: "2001"
            marts/finance/: "2002"
        page_title_prefix: "SQL Summary - "
        llm_provider: "openai"
        llm_model: "gpt-4.1-mini"
        llm_api_base_url: "https://api.openai.com/v1/chat/completions"
        git_diff_range: "HEAD~1..HEAD"
        cache_path: ".sql_confluence_cache.yml"
"""
                with tempfile.NamedTemporaryFile("w+", suffix=".yml", delete=False) as config_file:
                        config_file.write(yaml_content)
                        config_path = Path(config_file.name)

                os.environ["LLM_API_KEY"] = "test-api-key"
                app_config = load_config(config_path)
                repo_config = get_repository_config(app_config, "test-repo")

                self.assertEqual(repo_config.confluence_parent_page_map["marts/"], "2001")
                self.assertEqual(repo_config.confluence_parent_page_map["marts/finance/"], "2002")


if __name__ == "__main__":
    unittest.main()
