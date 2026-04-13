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
        prompt = self._build_prompt(sql_text, source_path)
        return self._call_provider(prompt)

    def describe_sql(self, sql_text: str, source_path: Optional[Path] = None) -> str:
        prompt = self._build_prompt(sql_text, source_path)
        return self._call_provider(prompt)

    def _build_prompt(self, sql_text: str, source_path: Optional[Path] = None) -> str:
        sections = [
            "You are an expert SQL documentation assistant.",
            "Analyze the following SQL and produce a structured Confluence-ready document.",
            "",
            "The document must contain these sections in order:",
            "",
            "## Overview",
            "Describe what this SQL does at a high level.",
            "Identify whether it is an ETL load, a report query, a transformation, or another type.",
            "If it loads a target table, state what kind of data it stores "
            "(for example: SCD Type 1, SCD Type 2, Fact, Dimension, Staging).",
            "",
            "## Tables Used",
            "List all source tables referenced in the SQL with a brief note on the role of each.",
            "",
            "## CTEs",
            "For each CTE explain its purpose, the tables it uses, any join or filter conditions, "
            "and any column translations or derivations.",
            "If there are no CTEs, write: None.",
            "",
            "## Joins",
            "List each join with the join type, the tables involved, and the join condition.",
            "If there are no joins, write: None.",
            "",
            "## Filters",
            "List all WHERE and HAVING conditions and explain the intent of each.",
            "If there are no filters, write: None.",
            "",
            "## Output",
            "Describe what the final result set produces.",
            "If the SQL writes to a target table or view, state the target name and what data it receives.",
            "",
            "Use clear markdown formatting with the headings above.",
            "Do not add information that is not present in the SQL.",
        ]
        if source_path:
            sections.append(f"\nSQL source file: {source_path}")
        sections.extend(["", "## SQL", "```sql", sql_text.strip(), "```"])
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
            "max_tokens": 1500,
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
