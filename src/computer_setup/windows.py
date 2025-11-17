"""Windows-specific helper functions implemented via PowerShell or Win32 APIs."""

from __future__ import annotations

import ctypes
import subprocess
import os
from pathlib import Path
from typing import Sequence
from winreg import HKEY_LOCAL_MACHINE, KEY_SET_VALUE, KEY_WRITE, OpenKey, SetValueEx, DeleteValue, REG_SZ


class CommandError(RuntimeError):
    pass


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def require_elevated() -> None:
    if not is_elevated():
        raise PermissionError("This command must be run from an elevated session")


def _escape_single_quotes(value: str) -> str:
    return value.replace("'", "''")


def _run_powershell(lines: Sequence[str]) -> subprocess.CompletedProcess[str]:
    script = "; ".join(lines)
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CommandError(result.stderr.strip() or result.stdout.strip())
    return result


def rename_computer(new_name: str) -> None:
    _run_powershell(
        [
            f"Rename-Computer -NewName '{_escape_single_quotes(new_name)}' -Force -ErrorAction Stop",
        ]
    )


def create_or_update_local_admin(username: str, password: str) -> None:
    escaped_user = _escape_single_quotes(username)
    escaped_pass = _escape_single_quotes(password)
    commands = [
        f"$SecurePassword = ConvertTo-SecureString '{escaped_pass}' -AsPlainText -Force",
        f"$existing = Get-LocalUser -Name '{escaped_user}' -ErrorAction SilentlyContinue",
        "if ($existing) {",
        "  Set-LocalUser -Name $existing.Name -Password $SecurePassword -PasswordNeverExpires $true -ErrorAction Stop",
        "} else {",
        f"  New-LocalUser -Name '{escaped_user}' -Password $SecurePassword -AccountNeverExpires -PasswordNeverExpires $true -ErrorAction Stop",
        "}",
        f"Add-LocalGroupMember -Group 'Administrators' -Member '{escaped_user}' -ErrorAction Stop",
    ]
    _run_powershell(commands)


def remove_local_user(username: str) -> None:
    escaped_user = _escape_single_quotes(username)
    commands = [
        f"$existing = Get-LocalUser -Name '{escaped_user}' -ErrorAction SilentlyContinue",
        "if ($existing) {",
        "  try {",
        "    Remove-LocalUser -Name $existing.Name -ErrorAction Stop",
        "  } catch {",
        "    throw \"Unable to remove local user $($existing.Name): $($_.Exception.Message)\"",
        "  }",
        "}",
    ]
    _run_powershell(commands)


def join_domain(domain: str, username: str, password: str, *, ou_path: str | None = None, restart: bool = False) -> None:
    escaped_user = _escape_single_quotes(username)
    escaped_pass = _escape_single_quotes(password)
    cmd = [
        f"$SecurePassword = ConvertTo-SecureString '{escaped_pass}' -AsPlainText -Force",
        f"$Credential = New-Object System.Management.Automation.PSCredential('{escaped_user}', $SecurePassword)",
        f"Add-Computer -DomainName '{_escape_single_quotes(domain)}' -Credential $Credential"
    ]
    if ou_path:
        cmd[-1] += f" -OUPath '{_escape_single_quotes(ou_path)}'"
    if restart:
        cmd[-1] += " -Restart"
    cmd[-1] += " -ErrorAction Stop"
    _run_powershell(cmd)


def _set_reg_values(key_path: str, values: dict[str, str]) -> None:
    with OpenKey(HKEY_LOCAL_MACHINE, key_path, 0, KEY_WRITE) as key:
        for name, data in values.items():
            SetValueEx(key, name, 0, REG_SZ, data)


def _delete_reg_values(key_path: str, names: Sequence[str]) -> None:
    with OpenKey(HKEY_LOCAL_MACHINE, key_path, 0, KEY_SET_VALUE) as key:
        for name in names:
            try:
                DeleteValue(key, name)
            except FileNotFoundError:
                continue


def configure_autologon(username: str, password: str) -> None:
    machine_name = os.environ.get("COMPUTERNAME", "localhost")
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    _set_reg_values(
        key_path,
        {
            "AutoAdminLogon": "1",
            "ForceAutoLogon": "1",
            "DefaultUserName": username,
            "DefaultPassword": password,
            "DefaultDomainName": machine_name,
        },
    )


def clear_autologon() -> None:
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    _set_reg_values(key_path, {"AutoAdminLogon": "0", "ForceAutoLogon": "0"})
    _delete_reg_values(key_path, ["DefaultPassword", "DefaultDomainName"])


def register_run_once(name: str, command: str) -> None:
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"
    _set_reg_values(key_path, {name: command})


def logoff_current_user() -> None:
    subprocess.run(["shutdown.exe", "/l"], check=True)


def restart_computer(delay_seconds: int = 5) -> None:
    subprocess.run(["shutdown.exe", "/r", "/t", str(delay_seconds)], check=True)

