# Set the test suite up on Windows: a Python environment of its own, and
# the browser it drives.  Run this once, from the directory it is in:
#
#     powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# Windows refuses to run unsigned scripts by default, which is what the
# -ExecutionPolicy is for; it applies to this one call and changes
# nothing about the machine.

function Fail($message) {
    Write-Host $message
    exit 1
}

Set-Location -Path $PSScriptRoot

$need = '3.10'
$check = 'import sys; raise SystemExit(sys.version_info < (3, 10))'

# Which python?  "py -3" is the launcher Windows installs, and is tried
# first because it finds an interpreter that is not on PATH.
if ($env:WEKO_E2E_PYTHON) {
    $candidates = @($env:WEKO_E2E_PYTHON)
    $named = $true
} else {
    $candidates = @('py -3', 'python', 'python3')
    $named = $false
}

$python = $null
foreach ($candidate in $candidates) {
    $parts = $candidate -split ' '
    $exe = $parts[0]
    if ($parts.Length -gt 1) {
        $pre = $parts[1..($parts.Length - 1)]
    } else {
        $pre = @()
    }
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    & $exe @pre -c $check 2>$null
    if ($LASTEXITCODE -eq 0) {
        $python = $exe
        $pythonArgs = $pre
        break
    }
    if ($named) {
        Fail "WEKO_E2E_PYTHON names $exe, which is not Python $need or newer."
    }
}

if (-not $python) {
    if ($named) {
        Fail "WEKO_E2E_PYTHON names $($candidates[0]), which is not there."
    }
    Fail @"
No Python $need or newer was found.

Tried: py -3, python, python3.  If yours is somewhere not on PATH, name
it:

    `$env:WEKO_E2E_PYTHON = 'C:\Python312\python.exe'
    powershell -ExecutionPolicy Bypass -File .\setup.ps1

$need is what the playwright and pytest in requirements.txt ask for; the
suite's own code is not what needs it.
"@
}

Write-Host "Using $python $pythonArgs ($(& $python @pythonArgs --version 2>&1))"

& $python @pythonArgs -m venv .venv-e2e
if ($LASTEXITCODE -ne 0) { Fail 'Could not create .venv-e2e.' }

# On Windows a virtual environment puts its programs in Scripts, not in
# bin, which is the one thing about this that is not the same as on Linux.
$venv = Join-Path $PSScriptRoot '.venv-e2e\Scripts\python.exe'
if (-not (Test-Path $venv)) { Fail "No interpreter at $venv." }

& $venv -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail 'Could not upgrade pip.' }
& $venv -m pip install -r (Join-Path $PSScriptRoot 'e2e\requirements.txt')
if ($LASTEXITCODE -ne 0) { Fail 'Could not install the requirements.' }
& $venv -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Fail 'Could not install chromium.' }

Write-Host ''
Write-Host 'Ready.  Now:'
Write-Host '    cd e2e'
Write-Host '    ..\.venv-e2e\Scripts\python .\e2ectl env     # what a run would use'
Write-Host '    ..\.venv-e2e\Scripts\python .\e2ectl ping    # can it reach the instance'
Write-Host '    ..\.venv-e2e\Scripts\python .\e2ectl doctor  # is it fit to test'
Write-Host '    ..\.venv-e2e\Scripts\python -m pytest        # run the base flow'
