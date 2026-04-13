import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests
import yaml


@dataclass
class ConfluenceManager:
    base_url: str
    space: str
    parent_page_id: str
    username: Optional[str] = None
    api_token: Optional[str] = None
    cache_path: str = ".sql_confluence_cache.yml"
    managed_section_start: str = "<!-- SQL_SUMMARY_START -->"
    managed_section_end: str = "<!-- SQL_SUMMARY_END -->"
    cache: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.base_url = self.base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.netloc.endswith("atlassian.net") and parsed.path in {"", "/"}:
            self.base_url = f"{self.base_url}/wiki"
        self.username = self.username or os.getenv("CONFLUENCE_USERNAME")
        self.api_token = self.api_token or os.getenv("CONFLUENCE_API_TOKEN")
        self.cache_file = Path(self.cache_path)
        self.load_cache()

    def auth(self):
        if not self.username or not self.api_token:
            raise ValueError("CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN must be set.")
        return (self.username, self.api_token)

    def load_cache(self) -> None:
        if self.cache_file.exists():
            self.cache = yaml.safe_load(self.cache_file.read_text(encoding="utf-8")) or {}
        else:
            self.cache = {}

    def save_cache(self) -> None:
        self.cache_file.write_text(yaml.safe_dump(self.cache), encoding="utf-8")

    def get_page_title(self, file_path: Path, repo_root: Path, prefix: str) -> str:
        relative_path = file_path.resolve().relative_to(repo_root.resolve())
        return f"{prefix}{relative_path.as_posix()}"

    def get_page_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/rest/api/content"
        params = {
            "title": title,
            "spaceKey": self.space,
            "expand": "body.storage,version",
        }
        response = requests.get(url, auth=self.auth(), params=params, timeout=30)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if response.status_code == 404:
                raise ValueError(
                    "Confluence content lookup returned 404. Check confluence_space uses the space key "
                    "(not display name), and ensure the configured user has access to that space."
                ) from exc
            raise
        results = response.json().get("results", [])
        return results[0] if results else None

    def create_page(self, title: str, content: str) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/content"
        payload = {
            "type": "page",
            "title": title,
            "ancestors": [{"id": int(self.parent_page_id)}],
            "space": {"key": self.space},
            "body": {
                "storage": {
                    "value": content,
                    "representation": "storage",
                }
            },
        }
        response = requests.post(url, auth=self.auth(), json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def update_page(self, page_id: str, title: str, content: str, version: int) -> Dict[str, Any]:
        url = f"{self.base_url}/rest/api/content/{page_id}"
        payload = {
            "id": page_id,
            "type": "page",
            "title": title,
            "version": {"number": version + 1},
            "body": {
                "storage": {
                    "value": content,
                    "representation": "storage",
                }
            },
        }
        response = requests.put(url, auth=self.auth(), json=payload, timeout=30)
        response.raise_for_status()
        return response.json()

    def _format_summary_html(self, summary_text: str) -> str:
        paragraphs = [f"<p>{line.strip()}</p>" for line in summary_text.split("\n") if line.strip()]
        return "\n".join(paragraphs)

    def build_managed_section(self, summary_text: str) -> str:
        content = self._format_summary_html(summary_text)
        return f"{self.managed_section_start}\n{content}\n{self.managed_section_end}"

    def merge_managed_section(self, old_content: str, summary_text: str) -> str:
        managed = self.build_managed_section(summary_text)
        if self.managed_section_start in old_content and self.managed_section_end in old_content:
            before, rest = old_content.split(self.managed_section_start, 1)
            _, after = rest.split(self.managed_section_end, 1)
            return f"{before}{managed}{after}"
        if old_content.strip():
            return f"{old_content}\n{managed}"
        return managed

    def publish_page(self, file_path: Path, repo_root: Path, summary_text: str, page_title_prefix: str) -> Dict[str, Any]:
        title = self.get_page_title(file_path, repo_root, page_title_prefix)
        page = self.get_page_by_title(title)
        if page:
            current_content = page["body"]["storage"]["value"]
            merged = self.merge_managed_section(current_content, summary_text)
            updated = self.update_page(page["id"], title, merged, page["version"]["number"])
            self.cache[str(file_path)] = page["id"]
            self.save_cache()
            return updated
        else:
            content = self.merge_managed_section("", summary_text)
            created = self.create_page(title, content)
            self.cache[str(file_path)] = created["id"]
            self.save_cache()
            return created
