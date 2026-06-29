# Telegram 연결 테스트 — .env 의 TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS 사용
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env 파일이 없습니다."
    exit 1
}

$envContent = Get-Content ".env" -Raw
$token = ([regex]::Match($envContent, 'TELEGRAM_BOT_TOKEN=([^\r\n#]+)')).Groups[1].Value.Trim()
$chatRaw = ([regex]::Match($envContent, 'TELEGRAM_ALLOWED_CHAT_IDS=([^\r\n#]+)')).Groups[1].Value.Trim()

if (-not $token) {
    Write-Host "ERROR: TELEGRAM_BOT_TOKEN 이 비어 있습니다. .env 를 저장했는지 확인하세요."
    exit 1
}
if (-not $chatRaw) {
    Write-Host "ERROR: TELEGRAM_ALLOWED_CHAT_IDS 가 비어 있습니다."
    exit 1
}

Write-Host "[1/2] getMe — 봇 토큰 확인..."
$me = Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getMe" -Method Get
Write-Host "  OK: @$($me.result.username) ($($me.result.first_name))"

$chatId = ($chatRaw -split ',')[0].Trim()
Write-Host "[2/2] sendMessage — chat_id $chatId 로 테스트 메시지 전송..."
$payload = @{
    chat_id = $chatId
    text    = "Infinite Trading Bot v4 — 텔레그램 연결 테스트 성공! $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
}
$json = $payload | ConvertTo-Json -Compress
$send = Invoke-RestMethod `
    -Uri "https://api.telegram.org/bot$token/sendMessage" `
    -Method Post `
    -ContentType "application/json; charset=utf-8" `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($json))
Write-Host "  OK: message_id=$($send.result.message_id)"
Write-Host ""
Write-Host "텔레그램 테스트 완료. 텔레그램 앱에서 메시지를 확인하세요."
