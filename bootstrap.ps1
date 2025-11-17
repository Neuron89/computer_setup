<#
    Bootstrap provisioning script
    -----------------------------

    1. Ensures the `uv` tool is available (installs it if missing).
    2. Executes the computer-setup CLI directly from the Git repository via `uvx`.

    Example (interactive) usage:

        iwr https://raw.githubusercontent.com/<your-org>/computer-setup/main/bootstrap.ps1 `
            -UseBasicParsing | iex

        bootstrap -Domain nycoa -AssignedUser johndoe `
            -ConfigPath \\fileserver\config\config.json
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$Domain,

    [Parameter(Mandatory = $true)]
    [string]$AssignedUser,

    [string]$ConfigPath = "config/config.json",

    [string]$InitialUser = $env:USERNAME,

    [string]$LocalAdmin = "WorkstationAdmin",

    [string]$GoogleCredentials,

    [string]$StatePath,

    [string]$Repository = "git+https://github.com/<your-org>/computer-setup.git"
)

function Assert-Elevated {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$currentIdentity
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run from an elevated PowerShell session."
    }
}

function Ensure-Uv {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return
    }
    Write-Host "Installing uv..." -ForegroundColor Cyan
    $installScriptUrl = "https://astral.sh/uv/install.ps1"
    try {
        Invoke-WebRequest $installScriptUrl -UseBasicParsing | Invoke-Expression
    } catch {
        throw "Failed to install uv: $($_.Exception.Message)"
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv installation did not succeed. Aborting."
    }
}

function Invoke-ComputerSetup {
    param(
        [string]$RepositorySpec
    )

    $argsList = @(
        $RepositorySpec,
        "--",
        "initial-run",
        "--domain", $Domain,
        "--assigned-user", $AssignedUser,
        "--initial-user", $InitialUser,
        "--local-admin", $LocalAdmin,
        "--config", $ConfigPath
    )

    if ($GoogleCredentials) {
        $argsList += @("--google-credentials", $GoogleCredentials)
    }
    if ($StatePath) {
        $argsList += @("--state", $StatePath)
    }

    Write-Host ("Running: uvx {0}" -f ($argsList -join " ")) -ForegroundColor Cyan
    $process = Start-Process -FilePath "uvx" -ArgumentList $argsList -Wait -PassThru -NoNewWindow
    if ($process.ExitCode -ne 0) {
        throw "computer-setup CLI exited with code $($process.ExitCode)"
    }
}

try {
    Assert-Elevated
    Ensure-Uv
    Invoke-ComputerSetup -RepositorySpec $Repository
    Write-Host "Bootstrap completed. Follow on-screen prompts." -ForegroundColor Green
} catch {
    Write-Error $_.Exception.Message
    exit 1
}

