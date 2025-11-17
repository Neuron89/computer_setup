"""Google Sheets helper functions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Tuple

import gspread

HEADERS = ["Domain", "Sequence", "Hostname", "AssignedUser", "Status", "Timestamp", "Notes"]


class SheetsClient:
    def __init__(self, credentials_path: Path):
        if not credentials_path.exists():
            raise FileNotFoundError(f"Google credentials file not found: {credentials_path}")
        self._client = gspread.service_account(filename=str(credentials_path))

    def _worksheet(self, sheet_id: str, worksheet: str):
        sh = self._client.open_by_key(sheet_id)
        ws = sh.worksheet(worksheet)
        self._ensure_header(ws)
        return ws

    @staticmethod
    def _ensure_header(ws) -> None:
        if not ws.row_count:
            ws.resize(rows=1, cols=len(HEADERS))
        headers = ws.row_values(1)
        if headers != HEADERS:
            ws.update("A1:G1", [HEADERS])

    def reserve_name(
        self,
        *,
        domain: str,
        assigned_user: str,
        sheet_id: str,
        worksheet: str,
        hostname_factory: Callable[[int], str],
    ) -> Tuple[int, str, str]:
        ws = self._worksheet(sheet_id, worksheet)
        records = ws.get_all_records()
        domain_lower = domain.lower()
        max_seq = 0
        for row in records:
            if str(row.get("Domain", "")).strip().lower() == domain_lower:
                try:
                    seq = int(row.get("Sequence", 0))
                    max_seq = max(max_seq, seq)
                except ValueError:
                    continue
        next_seq = max_seq + 1
        hostname = hostname_factory(next_seq)
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        row = [domain, next_seq, hostname, assigned_user, "Pending", timestamp, ""]
        result = ws.append_row(row, value_input_option="USER_ENTERED")
        updated_range = result["updates"]["updatedRange"]
        row_number = int(updated_range.split("!")[1].split(":")[0][1:])
        return next_seq, hostname, f"{worksheet}!A{row_number}:G{row_number}"

    def update_status(
        self,
        *,
        sheet_id: str,
        worksheet: str,
        row_range: str,
        status: str,
        notes: str = "",
    ) -> None:
        ws = self._worksheet(sheet_id, worksheet)
        # Extract row number from range like "Devices!A5:G5"
        parts = row_range.split("!")
        range_part = parts[-1]
        start_cell = range_part.split(":")[0]
        row_number = int("".join(filter(str.isdigit, start_cell)))
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        ws.update(
            f"E{row_number}:G{row_number}",
            [[status, timestamp, notes]],
        )

