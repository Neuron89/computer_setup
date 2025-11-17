# Computer Setup Automation

Python tooling for provisioning a freshly imaged Windows workstation:

- Creates a permanent local administrator account.
- Switches to the new admin context and removes the temporary build user.
- Joins the device to the requested Active Directory domain.
- Reserves and records computer names in a shared Google Sheet.

> ⚠️ **Prerequisites**
>
> - Run from an elevated PowerShell or terminal.  
> - Python 3.10+ on the device.  
> - `uv` installed (`pipx install uv` or download from https://github.com/astral-sh/uv).  
> - A Google Cloud service account with the Sheets API enabled and access to the tracking spreadsheet.

## Local setup

```powershell
uv sync
uv run computer-setup --help
```

## High-level workflow

1. `initial-run`  
   - Prompts for local admin + domain credentials.  
   - Reserves the next computer name in Google Sheets.  
   - Renames the machine, creates the admin account, configures auto-logon, and schedules the continuation task.  
   - Logs off, triggering the new admin to sign in automatically.

2. `post-login`  
   - Runs automatically on the first admin logon.  
   - Removes the build user, joins the domain, updates the spreadsheet row, and clears secrets/autologon data.

> The post-login command can be executed manually (`computer-setup post-login --state <path>`) if needed.

## Configuration

Copy `config/example-config.json` to `config/config.json`, then customise:

- `google_credentials`: absolute path to the Google service-account JSON.
- `domains`: key per environment (`nycoa`, `shawsheen`, …) with:
  - `sheet_id`: Google Sheet ID (from the URL).
  - `worksheet`: tab name to use.
  - `hostname_template`: e.g. `{seq:03d}-{user}`.
  - `ou_path`: optional AD OU distinguished name for the domain join.

### Spreadsheet layout

The automation will enforce the following header row (created automatically if missing):

| Domain | Sequence | Hostname | AssignedUser | Status | Timestamp | Notes |
|--------|----------|----------|--------------|--------|-----------|-------|

Each provisioning run appends a new row with status `Pending`, then updates the same row to `Joined` after the domain join completes.

### Secrets

Passwords are stored temporarily under `%ProgramData%\ComputerSetup\state.json`, encrypted with the Windows DPAPI (machine scope). The file is deleted as soon as the `post-login` step finishes.

## Zero-install bootstrap

Run `bootstrap.ps1` from an elevated PowerShell session on a freshly imaged machine:

```powershell
iwr https://raw.githubusercontent.com/Neuron89/computer_setup/main/bootstrap.ps1 `
    -UseBasicParsing | iex

bootstrap -Domain nycoa -AssignedUser johndoe `
    -ConfigPath \\fileserver\share\config.json `
    -GoogleCredentials \\fileserver\secure\service-account.json
```

What the script does:

- Confirms the shell is elevated before proceeding.
- Installs `uv` via the official installer when it is not already present.
- Invokes `uvx git+https://github.com/Neuron89/computer_setup.git -- initial-run ...` with the parameters you supply.

Key parameters:

- `-Domain`: domain slug matching an entry in `config.json`.
- `-AssignedUser`: person receiving the workstation (written to Google Sheets).
- `-ConfigPath`: path to the populated `config.json` (defaults to `config/config.json`).
- `-GoogleCredentials`: optional override for the service account JSON path.
- `-InitialUser`: optional override for the temporary build account (`$env:USERNAME` by default).
- `-LocalAdmin`: optional override for the permanent admin account name (`WorkstationAdmin` by default).
- `-StatePath`: optional override for where bootstrap should persist state between reboots.
- `-Repository`: alternate git source passed directly to `uvx` if you maintain a fork.

Secrets collected during execution live under `%ProgramData%\ComputerSetup\` and are encrypted with the Windows Data Protection API (machine scope) until the `post-login` phase removes them.

