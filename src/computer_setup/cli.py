"""Command-line interface for the computer setup automation."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from .config import AppConfig, load_config, slugify_user
from .security import protect_string, unprotect_string
from .sheets import SheetsClient
from .state import Secrets, SetupState, STATE_FILE, clear_state, load_state, save_state
from . import windows


def _resolve_config(path: Path | None) -> AppConfig:
    if path is None:
        raise ValueError("Configuration file path is required")
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    return load_config(path)


def _resolve_credentials_path(args_value: str | None, config: AppConfig) -> Path:
    if args_value:
        return Path(args_value).expanduser().resolve()
    if config.google_credentials:
        return config.google_credentials.expanduser().resolve()
    raise ValueError(
        "Google credentials path must be supplied via --google-credentials or the configuration file."
    )


def _prompt_password(prompt: str, confirm: bool = True) -> str:
    while True:
        pw1 = getpass.getpass(prompt)
        if not pw1:
            print("Password cannot be empty.")
            continue
        if not confirm:
            return pw1
        pw2 = getpass.getpass("Confirm password: ")
        if pw1 == pw2:
            return pw1
        print("Passwords do not match. Try again.")


def _initial_run(args: argparse.Namespace) -> None:
    windows.require_elevated()

    config_path = Path(args.config).expanduser().resolve()
    config = _resolve_config(config_path)
    domain_config = config.get_domain(args.domain)

    google_creds = _resolve_credentials_path(args.google_credentials, config)
    sheets = SheetsClient(google_creds)

    assigned_slug = slugify_user(args.assigned_user)

    seq, hostname, sheet_range = sheets.reserve_name(
        domain=args.domain,
        assigned_user=assigned_slug,
        sheet_id=domain_config.sheet_id,
        worksheet=domain_config.worksheet,
        hostname_factory=lambda n: domain_config.build_hostname(n, assigned_slug),
    )
    print(f"[+] Reserved hostname: {hostname} (sequence {seq:03d})")

    local_admin_password = _prompt_password(f"Enter password for local admin '{args.local_admin}': ")
    domain_username = input("Enter domain join username (DOMAIN\\user): ").strip()
    domain_password = _prompt_password("Enter domain join password: ", confirm=False)

    print("[+] Renaming computer...")
    windows.rename_computer(hostname)

    print("[+] Creating local administrator account...")
    windows.create_or_update_local_admin(args.local_admin, local_admin_password)

    print("[+] Configuring auto-logon for initial migration...")
    windows.configure_autologon(args.local_admin, local_admin_password)

    python_exe = Path(sys.executable).resolve()
    state_path = Path(args.state).expanduser().resolve()

    secrets = Secrets(
        local_admin_password=protect_string(local_admin_password),
        domain_username=domain_username,
        domain_password=protect_string(domain_password),
    )
    state = SetupState.create(
        domain=args.domain,
        assigned_user=assigned_slug,
        computer_name=hostname,
        initial_user=args.initial_user,
        local_admin_user=args.local_admin,
        sheet_id=domain_config.sheet_id,
        worksheet=domain_config.worksheet,
        sheet_range=sheet_range,
        secrets=secrets,
    )
    save_state(state, state_path)
    print(f"[+] State saved to {state_path}")

    run_once_command = (
        f'"{python_exe}" -m computer_setup.cli post-login '
        f'--state "{state_path}" --config "{config_path}"'
    )
    print("[+] Registering RunOnce continuation...")
    windows.register_run_once("ComputerSetupPostLogin", run_once_command)

    print("[!] Logging off current user to continue setup...")
    windows.logoff_current_user()


def _post_login(args: argparse.Namespace) -> None:
    windows.require_elevated()
    state_path = Path(args.state).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()

    state = load_state(state_path)
    config = _resolve_config(config_path)
    domain_config = config.get_domain(state.domain)

    google_creds = _resolve_credentials_path(args.google_credentials, config)
    sheets = SheetsClient(google_creds)

    domain_password = unprotect_string(state.secrets.domain_password)

    print("[+] Clearing auto-logon configuration...")
    windows.clear_autologon()

    print(f"[+] Removing build user '{state.initial_user}'...")
    if state.initial_user.lower() != state.local_admin_user.lower():
        windows.remove_local_user(state.initial_user)

    print(f"[+] Joining domain {state.domain}...")
    windows.join_domain(
        state.domain,
        state.secrets.domain_username,
        domain_password,
        ou_path=domain_config.ou_path,
        restart=False,
    )

    print("[+] Updating Google Sheet status...")
    sheets.update_status(
        sheet_id=state.sheet_id,
        worksheet=state.worksheet,
        row_range=state.sheet_range,
        status="Joined",
        notes="Provisioned via computer-setup",
    )

    print("[+] Cleaning up stored state...")
    clear_state(state_path)

    if not args.no_restart:
        print("[!] Restarting computer in 10 seconds...")
        windows.restart_computer(delay_seconds=10)
    else:
        print("[!] Restart skipped (use --no-restart).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automate Windows workstation provisioning.")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config/config.json", help="Path to configuration JSON.")
    common.add_argument("--google-credentials", help="Path to Google service-account JSON (overrides config).")

    init_parser = sub.add_parser("initial-run", parents=[common], help="Run from the temporary build account.")
    init_parser.add_argument("--domain", required=True, help="Domain key from configuration.")
    init_parser.add_argument("--assigned-user", required=True, help="User slug to embed in hostname.")
    init_parser.add_argument("--initial-user", default=getpass.getuser(), help="Temporary account to remove later.")
    init_parser.add_argument("--local-admin", default="WorkstationAdmin", help="Permanent local admin username.")
    init_parser.add_argument("--state", default=str(STATE_FILE), help="Override state file location.")
    init_parser.set_defaults(func=_initial_run)

    post_parser = sub.add_parser("post-login", parents=[common], help="Continuation after auto logon.")
    post_parser.add_argument("--state", default=str(STATE_FILE), help="State file location.")
    post_parser.add_argument("--no-restart", action="store_true", help="Skip automatic restart after domain join.")
    post_parser.set_defaults(func=_post_login)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

