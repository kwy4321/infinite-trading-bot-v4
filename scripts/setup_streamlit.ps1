# Windows — Streamlit 대시보드 로컬 실행
# 사용: powershell -ExecutionPolicy Bypass -File scripts/setup_streamlit.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Find-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host "Python 없음 — https://python.org 에서 설치 후 다시 실행"
    exit 1
}

Write-Host "Python: $py"

if (-not (Test-Path ".venv")) {
    & $py -m venv .venv
}
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
& $venvPy -m pip install -q -U pip
& $venvPy -m pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host ".env 생성됨 — 키 입력 후 다시 실행하세요."
    exit 0
}

Write-Host ""
Write-Host "Streamlit 시작 — 브라우저: http://localhost:8501"
Write-Host "종료: Ctrl+C"
Write-Host ""

& (Join-Path $Root ".venv\Scripts\streamlit.exe") run dashboard/streamlit_app.py `
    --server.port 8501 `
    --server.address localhost
