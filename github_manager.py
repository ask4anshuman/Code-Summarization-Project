import base64
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests


@dataclass
class GithubManager:
    repo: str
    token: str
    api_base_url: str

    @classmethod
    def from_env(cls, repo: str, api_base_url: str) -> "GithubManager":
        token = (os.getenv("SQL_GITHUB_TOKEN", "") or os.getenv("GITHUB_TOKEN", "")).strip()
        if not token:
            raise ValueError(
                "GitHub token is missing. Set SQL_GITHUB_TOKEN (preferred) or GITHUB_TOKEN for PR integration."
            )
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
                        "and whether SQL_GITHUB_TOKEN can access that repository."
                    ) from exc
                if path.startswith(f"/repos/{self.repo}"):
                    raise ValueError(
                        f"GitHub repository '{self.repo}' was not found. Check github_repo in YAML "
                        "and ensure SQL_GITHUB_TOKEN has access to that repository."
                    ) from exc
            if response.status_code in {401, 403}:
                raise ValueError(
                    "GitHub API request was denied. Check SQL_GITHUB_TOKEN validity and repository permissions."
                ) from exc
            raise
        return response

    def get_pr_head_sha(self, pr_number: int) -> str:
        response = self._request("GET", f"/repos/{self.repo}/pulls/{pr_number}")
        return response.json()["head"]["sha"]

    def get_pr(self, pr_number: int) -> Dict[str, object]:
        response = self._request("GET", f"/repos/{self.repo}/pulls/{pr_number}")
        return response.json()

    def get_pr_refs(self, pr_number: int) -> Dict[str, str]:
        payload = self.get_pr(pr_number)
        base_sha = str(payload.get("base", {}).get("sha", ""))
        head_sha = str(payload.get("head", {}).get("sha", ""))
        if not base_sha or not head_sha:
            raise ValueError(f"Unable to resolve base/head refs for PR #{pr_number}.")
        return {"base": base_sha, "head": head_sha}

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

    def list_pr_sql_file_changes(self, pr_number: int) -> List[Dict[str, str]]:
        sql_files: List[Dict[str, str]] = []
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
                previous_filename = item.get("previous_filename", "")
                status = item.get("status", "")
                if filename.lower().endswith(".sql") or previous_filename.lower().endswith(".sql"):
                    sql_files.append(
                        {
                            "filename": filename,
                            "previous_filename": previous_filename,
                            "status": status,
                        }
                    )

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

    def get_file_content_if_exists(self, path: str, ref: str) -> Optional[str]:
        url = f"{self.api_base_url}/repos/{self.repo}/contents/{path}"
        response = requests.request(
            "GET",
            url,
            headers=self._headers(),
            params={"ref": ref},
            timeout=30,
        )
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if response.status_code in {401, 403}:
                raise ValueError(
                    "GitHub API request was denied. Check SQL_GITHUB_TOKEN validity and repository permissions."
                ) from exc
            raise

        payload = response.json()
        encoded = payload.get("content", "")
        if payload.get("encoding") != "base64" or not encoded:
            raise ValueError(f"Unable to decode content for '{path}' from GitHub API response.")
        decoded = base64.b64decode(encoded)
        return decoded.decode("utf-8")

    def get_pr_sql_file_contents(self, pr_number: int, ref: Optional[str] = None) -> Dict[str, str]:
        resolved_ref = ref or self.get_pr_head_sha(pr_number)
        sql_files = self.list_pr_sql_files(pr_number)
        return {path: self.get_file_content(path, resolved_ref) for path in sql_files}

    def list_issue_comments(self, pr_number: int) -> List[Dict[str, object]]:
        page = 1
        comments: List[Dict[str, object]] = []
        while True:
            response = self._request(
                "GET",
                f"/repos/{self.repo}/issues/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            items = response.json()
            if not items:
                break
            comments.extend(items)
            if len(items) < 100:
                break
            page += 1
        return comments

    def find_pr_comment(self, pr_number: int, marker: str) -> Optional[Dict[str, object]]:
        matching_comments: List[Dict[str, object]] = []
        for comment in self.list_issue_comments(pr_number):
            body = comment.get("body", "")
            if isinstance(body, str) and marker in body:
                matching_comments.append(comment)
        if not matching_comments:
            return None

        def _sort_key(comment: Dict[str, object]) -> tuple[str, int]:
            created_at = str(comment.get("created_at", ""))
            try:
                comment_id = int(comment.get("id", 0))
            except (TypeError, ValueError):
                comment_id = 0
            return (created_at, comment_id)

        return max(matching_comments, key=_sort_key)

    def create_pr_comment(self, pr_number: int, body: str) -> Dict[str, str]:
        response = self._request(
            "POST",
            f"/repos/{self.repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        return response.json()

    def update_pr_comment(self, comment_id: int, body: str) -> Dict[str, str]:
        response = self._request(
            "PATCH",
            f"/repos/{self.repo}/issues/comments/{comment_id}",
            json={"body": body},
        )
        return response.json()

    def upsert_pr_comment(self, pr_number: int, marker: str, body: str) -> Dict[str, str]:
        existing = self.find_pr_comment(pr_number, marker)
        if existing is None:
            return self.create_pr_comment(pr_number, body)
        return self.update_pr_comment(int(existing["id"]), body)
