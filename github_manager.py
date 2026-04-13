import base64
import os
from dataclasses import dataclass
from typing import Dict, List

import requests


@dataclass
class GithubManager:
    repo: str
    token: str
    api_base_url: str

    @classmethod
    def from_env(cls, repo: str, api_base_url: str) -> "GithubManager":
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable must be set for PR integration.")
        if not api_base_url:
            raise ValueError("github_base_url must be set in config for PR integration.")
        return cls(repo=repo, token=token, api_base_url=api_base_url.rstrip("/"))

    def _headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.api_base_url}{path}"
        response = requests.request(method, url, headers=self._headers(), timeout=30, **kwargs)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if response.status_code == 404:
                if "/pulls/" in path:
                    raise ValueError(
                        f"GitHub PR not found for '{self.repo}'. Check github_repo, the PR number, "
                        "and whether GITHUB_TOKEN can access that repository."
                    ) from exc
                if path.startswith(f"/repos/{self.repo}"):
                    raise ValueError(
                        f"GitHub repository '{self.repo}' was not found. Check github_repo in YAML "
                        "and ensure GITHUB_TOKEN has access to that repository."
                    ) from exc
            if response.status_code in {401, 403}:
                raise ValueError(
                    "GitHub API request was denied. Check GITHUB_TOKEN validity and repository permissions."
                ) from exc
            raise
        return response

    def get_pr_head_sha(self, pr_number: int) -> str:
        response = self._request("GET", f"/repos/{self.repo}/pulls/{pr_number}")
        return response.json()["head"]["sha"]

    def list_pr_sql_files(self, pr_number: int) -> List[str]:
        sql_files: List[str] = []
        page = 1
        while True:
            response = self._request(
                "GET",
                f"/repos/{self.repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            files = response.json()
            if not files:
                break

            for item in files:
                filename = item.get("filename", "")
                status = item.get("status", "")
                if filename.lower().endswith(".sql") and status != "removed":
                    sql_files.append(filename)

            if len(files) < 100:
                break
            page += 1

        return sql_files

    def get_file_content(self, path: str, ref: str) -> str:
        response = self._request(
            "GET",
            f"/repos/{self.repo}/contents/{path}",
            params={"ref": ref},
        )
        payload = response.json()
        encoded = payload.get("content", "")
        if payload.get("encoding") != "base64" or not encoded:
            raise ValueError(f"Unable to decode content for '{path}' from GitHub API response.")
        decoded = base64.b64decode(encoded)
        return decoded.decode("utf-8")

    def get_pr_sql_file_contents(self, pr_number: int) -> Dict[str, str]:
        head_sha = self.get_pr_head_sha(pr_number)
        sql_files = self.list_pr_sql_files(pr_number)
        return {path: self.get_file_content(path, head_sha) for path in sql_files}

    def create_pr_comment(self, pr_number: int, body: str) -> Dict[str, str]:
        response = self._request(
            "POST",
            f"/repos/{self.repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        return response.json()
