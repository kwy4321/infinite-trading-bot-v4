# DRY_RUN 로컬 테스트용 스크립트
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Find-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:USERPROFILE\miniconda3\python.exe",
        "$env:USERPROFILE\anaconda3\python.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        $ver = & $cmd.Source -c "import sys; print(sys.version)" 2>$null
        if ($LASTEXITCODE -eq 0) { return $cmd.Source }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "Python을 찾지 못했습니다. python.org 에서 설치 후 PATH에 추가하세요."
    exit 1
}

Write-Host "Python: $py"
& $py -m pip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env 파일을 만들었습니다. TELEGRAM_BOT_TOKEN 과 TELEGRAM_ALLOWED_CHAT_IDS 를 채운 뒤 다시 실행하세요."
    exit 0
}

$envContent = Get-Content ".env" -Raw
$token = ([regex]::Match($envContent, 'TELEGRAM_BOT_TOKEN=([^\r\n#]+)')).Groups[1].Value.Trim()
if (-not $token) {
    Write-Host "`.env` 에 TELEGRAM_BOT_TOKEN 을 입력해주세요."
    exit 1
}

Write-Host "봇 시작 (DRY_RUN) — Ctrl+C 로 종료"
& $py main.py
