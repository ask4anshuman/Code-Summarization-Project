from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests


@dataclass
class LLMService:
    provider: str = ""
    model: str = ""
    api_key: Optional[str] = None
    api_base_url: Optional[str] = None

    def summarize_sql(self, sql_text: str, source_path: Optional[Path] = None) -> str:
        prompt = self._build_summary_prompt(sql_text, source_path)
        return self._call_provider(prompt)

    def describe_sql(self, sql_text: str, source_path: Optional[Path] = None) -> str:
        prompt = self._build_description_prompt(sql_text, source_path)
        return self._call_provider(prompt)

    def _build_summary_prompt(self, sql_text: str, source_path: Optional[Path] = None) -> str:
        sections = [
            "You are an expert SQL documentation assistant.",
            "Summarize the SQL logic in human-readable form.",
            "Cover tables, CTEs, join types, filters, and the overall query purpose.",
            "Do not add information that is not present in the SQL.",
        ]
        if source_path:
            sections.append(f"SQL source path: {source_path}")
        sections.extend(["SQL:", sql_text.strip()])
        return "\n".join(str(line) for line in sections)

    def _build_description_prompt(self, sql_text: str, source_path: Optional[Path] = None) -> str:
        sections = [
            "You are an expert SQL documentation assistant.",
            "Analyze the following SQL and explain it clearly.",
            "Provide separate coverage for:",
            "1. the number of tables used and their names,",
            "2. any CTEs used and what each CTE is doing,",
            "3. join types and the tables involved in each join,",
            "4. filters applied in WHERE and HAVING clauses,",
            "5. the overall purpose of the query.",
            "If a section does not apply, say 'None'.",
            "Do not add information that is not present in the SQL."
            "Generate the document in clear markdown format with appropriate headings for each section.",
            "This document will be published to Confluence, so use formatting that works well in Confluence pages."
        ]
        if source_path:
            sections.append(f"SQL source path: {source_path}")
        sections.extend(["SQL:", sql_text.strip()])
        return "\n".join(str(line) for line in sections)

    def _call_provider(self, prompt: str) -> str:
        if self.provider == "local":
            return self._local_fallback(prompt)

        if not self.api_key:
            raise ValueError("LLM API key must be set to use the configured LLM provider.")
        if not self.api_base_url:
            raise ValueError("LLM API base URL must be set to use the configured LLM provider.")

        url = self.api_base_url
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that summarizes SQL code."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 600,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"].strip()

    def _local_fallback(self, prompt: str) -> str:
        return (
            "SQL Description (local fallback):\n"
            "Use an external LLM provider to generate richer output.\n\n"
            "Prompt received:\n"
            f"{prompt}"
        )
