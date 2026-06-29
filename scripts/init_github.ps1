# GitHub first upload (Git for Windows required)
# Terminal messages in English to avoid Korean garbled text on Windows.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Find-Git {
    $candidates = @(
        "$env:ProgramFiles\Git\cmd\git.exe",
        "$env:ProgramFiles\Git\bin\git.exe",
        "${env:ProgramFiles(x86)}\Git\cmd\git.exe",
        "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command git -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$gitExe = Find-Git
if (-not $gitExe) {
    Write-Host "ERROR: Git not found. Install from https://git-scm.com/download/win"
    Read-Host "Press Enter to exit"
    exit 1
}

$gitDir = Split-Path -Parent $gitExe
$env:Path = "$gitDir;" + $env:Path
Write-Host "Git  : $gitExe"
Write-Host "Folder: $Root"
Write-Host ""

if (-not (Test-Path ".git")) {
    & $gitExe init
    & $gitExe branch -M main
}

# Step 1: Git user (required for commit)
$gitName = (& $gitExe config user.name 2>$null)
$gitEmail = (& $gitExe config user.email 2>$null)
if (-not $gitName) {
    Write-Host "[Step 1/4] Your name (GitHub username is OK)"
    $gitName = Read-Host "Name"
    if (-not $gitName) { exit 1 }
    & $gitExe config user.name $gitName
}
if (-not $gitEmail) {
    Write-Host "[Step 1/4] Your email (same as GitHub signup email)"
    $gitEmail = Read-Host "Email"
    if (-not $gitEmail) { exit 1 }
    & $gitExe config user.email $gitEmail
}
Write-Host "Author: $gitName <$gitEmail>"
Write-Host ""

# Step 2: stage files (.env is NOT uploaded - in .gitignore)
& $gitExe add .
$status = & $gitExe status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit."
    Read-Host "Press Enter to exit"
    exit 0
}

Write-Host "[Step 2/4] Files ready to upload:"
& $gitExe status -sb
Write-Host ""

# Step 3: GitHub URL
Write-Host "[Step 3/4] GitHub repo URL"
Write-Host "Example: https://github.com/kwy4321/infinite-trading-bot-v4.git"
$repo = Read-Host "Repo URL"
if (-not $repo) { exit 1 }

$remotes = & $gitExe remote
if ($remotes -contains 'origin') {
    & $gitExe remote set-url origin $repo
} else {
    & $gitExe remote add origin $repo
}

# Step 4: commit + push
Write-Host ""
Write-Host "[Step 4/4] Commit message (press Enter for default)"
$msg = Read-Host "Message"
if (-not $msg) { $msg = "Initial commit: infinite trading bot v4" }

Write-Host "Committing..."
& $gitExe commit -m $msg
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "COMMIT FAILED - see error above."
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Pushing to GitHub... (login window may appear)"
& $gitExe push -u origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "PUSH FAILED."
    Write-Host "- Sign in to GitHub if prompted."
    Write-Host "- Check repo exists and is empty on github.com"
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "========================================"
Write-Host "  SUCCESS! Uploaded to GitHub"
Write-Host "  $repo"
Write-Host "========================================"
Write-Host ""
Write-Host "On your server run:"
Write-Host "  bash scripts/server_setup.sh $repo"
Read-Host "Press Enter to exit"
