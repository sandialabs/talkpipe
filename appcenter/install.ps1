#Requires -Version 5.1
<#
Open the TalkPipe App Center with one command (PowerShell):

  powershell -ExecutionPolicy Bypass -c "irm https://github.com/sandialabs/talkpipe/releases/latest/download/install.ps1 | iex"

What it does: installs uv (https://docs.astral.sh/uv/) into %USERPROFILE%\.local\bin
if it is missing, then hands over to the App Center itself, one Python file that uv
runs in its own cached environment:

  uv run https://github.com/sandialabs/talkpipe/releases/latest/download/talkpipe_appcenter.py

To act without the screen, run that `uv run` line yourself with arguments,
e.g. `uv run <url> install vault` (a piped `irm | iex` cannot receive them).

uv is the only thing this script installs. The App Center installs applications
with `uv tool install`, each into its own environment; nothing else on the
machine is touched.
#>
$ErrorActionPreference = "Stop"

$AppCenterUrl = "https://github.com/sandialabs/talkpipe/releases/latest/download/talkpipe_appcenter.py"

function Start-AppCenter {
    $localBin = Join-Path $env:USERPROFILE ".local\bin"
    Write-Host "==> [1/2] Checking for uv, the Python package manager the App Center uses"
    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uv -and (Test-Path (Join-Path $localBin "uv.exe"))) { $uv = Join-Path $localBin "uv.exe" }
    if ($uv) {
        Write-Host "Found uv at $uv."
    } else {
        Write-Host "Not found. Downloading it from astral.sh into $localBin..."
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $uv = Join-Path $localBin "uv.exe"
        if (-not (Test-Path $uv)) { throw "uv did not install to $uv; see https://docs.astral.sh/uv/getting-started/installation/" }
        Write-Host "Installed uv."
    }

    Write-Host "==> [2/2] Starting the TalkPipe App Center"
    Write-Host "(the first run fetches its Python and one library; later runs are quick)"
    # Native commands write progress to stderr; under Windows PowerShell 5.1
    # that must not be a terminating error.
    $ErrorActionPreference = "Continue"
    & $uv run $AppCenterUrl @args
    exit $LASTEXITCODE
}

Start-AppCenter @args
