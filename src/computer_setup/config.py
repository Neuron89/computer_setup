"""Configuration loading."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DomainConfig:
    name: str
    sheet_id: str
    worksheet: str
    hostname_template: str
    ou_path: Optional[str]

    def build_hostname(self, seq: int, username: str) -> str:
        return self.hostname_template.format(seq=seq, user=username)


@dataclass
class AppConfig:
    google_credentials: Optional[Path]
    domains: dict[str, DomainConfig]

    def get_domain(self, name: str) -> DomainConfig:
        key = name.lower()
        if key not in self.domains:
            raise KeyError(f"Domain '{name}' not present in configuration")
        return self.domains[key]


def load_config(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)

    credentials_path = data.get("google_credentials")
    if credentials_path:
        credentials_path = Path(credentials_path)

    domains: dict[str, DomainConfig] = {}
    for key, value in data.get("domains", {}).items():
        domains[key.lower()] = DomainConfig(
            name=key,
            sheet_id=value["sheet_id"],
            worksheet=value.get("worksheet", "Devices"),
            hostname_template=value.get("hostname_template", "{seq:03d}-{user}"),
            ou_path=value.get("ou_path"),
        )

    if not domains:
        raise ValueError("Configuration file must define at least one domain entry")

    return AppConfig(google_credentials=credentials_path, domains=domains)


_USER_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify_user(value: str) -> str:
    slug = _USER_SLUG_RE.sub("-", value.strip().lower())
    slug = slug.strip("-")
    return slug or "user"

