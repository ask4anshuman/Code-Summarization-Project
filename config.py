"""Configuration models and YAML loading utilities.

This module is used by cli.py to load repository settings from sql_confluence.yml
and validate required fields before any preview/publish operation runs.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import yaml
except ImportError as exc:
    raise ImportError(
        "PyYAML is required to load YAML config files. Install it with `pip install pyyaml`."
    ) from exc


@dataclass
class RepositoryConfig:
    name: str
    repo_root: str = "."
    github_repo: str = ""
    github_base_url: str = ""
    sql_glob: str = "**/*.sql"
    confluence_base_url: str = ""
    confluence_space: str = ""
    confluence_parent_page_id: str = ""
    confluence_parent_page_map: Dict[str, str] = field(default_factory=dict)
    page_title_prefix: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_base_url: Optional[str] = ""
    git_diff_range: str = "HEAD~1..HEAD"
    cache_path: str = ".sql_confluence_cache.yml"
    managed_section_start: str = "<!-- SQL_SUMMARY_START -->"
    managed_section_end: str = "<!-- SQL_SUMMARY_END -->"

    def resolve_repo_root(self, config_dir: Path) -> Path:
        repo_path = Path(self.repo_root)
        return repo_path.resolve() if repo_path.is_absolute() else (config_dir / repo_path).resolve()

    def get_llm_api_key(self) -> Optional[str]:
        return os.getenv("LLM_API_KEY")

    def validate(self) -> None:
        if not self.name:
            raise ValueError("Repository config must include a non-empty name.")
        if not self.confluence_base_url:
            raise ValueError("Repository config must include confluence_base_url.")
        if not self.confluence_space:
            raise ValueError("Repository config must include confluence_space.")
        if not self.confluence_parent_page_id:
            raise ValueError("Repository config must include confluence_parent_page_id.")
        if not isinstance(self.confluence_parent_page_map, dict):
            raise ValueError("confluence_parent_page_map must be a mapping of path prefixes to page ids.")
        for path_prefix, parent_id in self.confluence_parent_page_map.items():
            if not isinstance(path_prefix, str) or not path_prefix.strip():
                raise ValueError("confluence_parent_page_map keys must be non-empty strings.")
            if not isinstance(parent_id, str) or not parent_id.strip():
                raise ValueError("confluence_parent_page_map values must be non-empty page-id strings.")
        if self.github_repo and not self.github_base_url:
            raise ValueError("Repository config must include github_base_url when github_repo is set.")
        if not self.llm_provider:
            raise ValueError("Repository config must include a non-empty llm_provider.")
        if self.llm_provider != "local":
            if not self.llm_model:
                raise ValueError("Repository config must include a non-empty llm_model.")
            if not self.get_llm_api_key():
                raise ValueError("LLM_API_KEY environment variable must be set for non-local providers.")
            if not self.llm_api_base_url:
                raise ValueError("Repository config must include a non-empty llm_api_base_url.")


@dataclass
class AppConfig:
    repositories: List[RepositoryConfig] = field(default_factory=list)


def _load_yaml_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _normalize_config(data: Any) -> Dict[str, Any]:
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    raise ValueError("Configuration file must contain a YAML mapping.")


def _normalize_repository_config(item: Dict[str, Any]) -> Dict[str, Any]:
    key_map = {
        "ai_provider": "llm_provider",
        "ai_model": "llm_model",
        "ai_api_base_url": "llm_api_base_url",
    }
    return {key_map.get(key, key): value for key, value in item.items()}


def load_config(config_path: Union[str, Path]) -> AppConfig:
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    raw = _load_yaml_file(config_path)
    config = _normalize_config(raw)
    repositories = []

    if "repositories" in config:
        if not isinstance(config["repositories"], list):
            raise ValueError("The 'repositories' key must be a list.")
        repository_items = config["repositories"]
    elif "repository" in config:
        repository_items = [config["repository"]]
    else:
        repository_items = [config]

    for item in repository_items:
        if not isinstance(item, dict):
            raise ValueError("Each repository entry must be a mapping.")
        normalized_item = _normalize_repository_config(item)
        repository = RepositoryConfig(**normalized_item)
        repository.validate()
        repositories.append(repository)

    if not repositories:
        raise ValueError("No repositories configured in the config file.")

    return AppConfig(repositories=repositories)


def get_repository_config(app_config: AppConfig, name: Optional[str] = None) -> RepositoryConfig:
    if name:
        for repo in app_config.repositories:
            if repo.name == name:
                return repo
        raise ValueError(f"Repository config not found for name: {name}")
    if len(app_config.repositories) == 1:
        return app_config.repositories[0]
    raise ValueError(
        "Multiple repositories are configured. Please specify the repository name with --repo."
    )
