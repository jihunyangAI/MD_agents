# send_telegram.ps1 - Send one Telegram message (HTML, UTF-8) using mail_config.json
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\send_telegram.ps1 -MessageFile tmp\msg.txt
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\send_telegram.ps1 -MessageFile tmp\msg.txt -DryRun
# Exit codes: 0 = sent (or dry run ok), 2 = skipped (token/chat_id missing), 1 = failed after retry
param(
    [Parameter(Mandatory = $true)][string]$MessageFile,
    [switch]$DryRun,
    [string]$ResponseFile
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cfg = Get-Content (Join-Path $root 'mail_config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$token = [string]$cfg.telegram.bot_token
$chatId = [string]$cfg.telegram.chat_id

# Resolve ${VAR} references from the env file named in telegram.env_file (e.g. .env.local)
$envVars = @{}
if ($cfg.telegram.env_file) {
    $envPath = Join-Path $root $cfg.telegram.env_file
    if (Test-Path $envPath) {
        foreach ($line in Get-Content $envPath -Encoding UTF8) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') { $envVars[$Matches[1]] = $Matches[2].Trim('"', "'") }
        }
    }
}
function Resolve-Value([string]$v) {
    if ($v -match '^\$\{(.+)\}$') { return [string]$envVars[$Matches[1]] }
    return $v
}
$token = Resolve-Value $token
$chatId = Resolve-Value $chatId

if (-not $token -or -not $chatId -or $token -match 'YOUR|PLACEHOLDER|xxx' -or $chatId -match 'YOUR|PLACEHOLDER|xxx') {
    Write-Output 'Telegram: bot_token/chat_id not set - skipped.'
    exit 2
}

# ReadAllText returns a plain .NET string; Get-Content -Raw adds PS note properties that
# ConvertTo-Json (PS 5.1) would serialize as {"value": ...}
$text = [System.IO.File]::ReadAllText((Join-Path $root $MessageFile), [System.Text.Encoding]::UTF8)
if ($DryRun) {
    Write-Output ("Telegram dry run: chat_id={0}, token=...{1}, chars={2}" -f $chatId, $token.Substring($token.Length - 4), $text.Length)
    exit 0
}

$body = @{ chat_id = $chatId; text = $text; parse_mode = 'HTML'; disable_web_page_preview = $true } | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$uri = "https://api.telegram.org/bot$token/sendMessage"

for ($i = 1; $i -le 2; $i++) {
    try {
        $r = Invoke-RestMethod -Uri $uri -Method Post -ContentType 'application/json; charset=utf-8' -Body $bytes
        if ($ResponseFile) {
            $json = $r | ConvertTo-Json -Depth 10
            [System.IO.File]::WriteAllText((Join-Path $root $ResponseFile), $json, (New-Object System.Text.UTF8Encoding($false)))
        }
        if ($r.ok) { Write-Output "Telegram: sent (message_id=$($r.result.message_id))"; exit 0 }
    } catch {
        Write-Output "Telegram: attempt $i failed - $($_.Exception.Message)"
    }
    if ($i -eq 1) { Start-Sleep -Seconds 2 }
}
Write-Output 'Telegram: WARNING - send failed after retry.'
exit 1
