"""State file helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STATE_DIR = Path(r"C:\ProgramData\ComputerSetup")
STATE_FILE = STATE_DIR / "state.json"


@dataclass
class Secrets:
    local_admin_password: str
    domain_username: str
    domain_password: str


@dataclass
class SetupState:
    version: int
    domain: str
    assigned_user: str
    computer_name: str
    initial_user: str
    local_admin_user: str
    sheet_id: str
    worksheet: str
    sheet_range: str
    secrets: Secrets = field(repr=False)

    @classmethod
    def create(
        cls,
        *,
        domain: str,
        assigned_user: str,
        computer_name: str,
        initial_user: str,
        local_admin_user: str,
        sheet_id: str,
        worksheet: str,
        sheet_range: str,
        secrets: Secrets,
    ) -> "SetupState":
        return cls(
            version=1,
            domain=domain,
            assigned_user=assigned_user,
            computer_name=computer_name,
            initial_user=initial_user,
            local_admin_user=local_admin_user,
            sheet_id=sheet_id,
            worksheet=worksheet,
            sheet_range=sheet_range,
            secrets=secrets,
        )

    def to_json(self) -> dict[str, Any]:
        result = asdict(self)
        return result

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SetupState":
        secrets = data.get("secrets") or {}
        return cls(
            version=data.get("version", 1),
            domain=data["domain"],
            assigned_user=data["assigned_user"],
            computer_name=data["computer_name"],
            initial_user=data["initial_user"],
            local_admin_user=data["local_admin_user"],
            sheet_id=data["sheet_id"],
            worksheet=data["worksheet"],
            sheet_range=data["sheet_range"],
            secrets=Secrets(
                local_admin_password=secrets["local_admin_password"],
                domain_username=secrets["domain_username"],
                domain_password=secrets["domain_password"],
            ),
        )


def save_state(state: SetupState, path: Path = STATE_FILE) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = state.to_json()
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return path


def load_state(path: Path = STATE_FILE) -> SetupState:
    with path.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    return SetupState.from_json(data)


def clear_state(path: Path = STATE_FILE) -> None:
    if path.exists():
        path.unlink()

