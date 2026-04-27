$ErrorActionPreference = "Stop"

$root = "C:\Users\amire\AI\stockmolt"
$python = "C:\Users\amire\AppData\Local\Programs\Python\Python312\python.exe"
$logDir = Join-Path $root "logs"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

function Start-Bot {
    param(
        [string]$ScriptName,
        [string]$LogName
    )

    $scriptPath = Join-Path $root $ScriptName
    $logPath = Join-Path $logDir $LogName

    Start-Process `
        -FilePath $python `
        -ArgumentList @($scriptPath) `
        -WorkingDirectory $root `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError $logPath `
        -WindowStyle Hidden
}

Start-Bot -ScriptName "Gemini_krx_bot_v2.py" -LogName "gemini_bot.log"
Start-Bot -ScriptName "Stockmolt bot groq.py" -LogName "groq_bot.log"

Write-Host "Started free-tier bots:"
Write-Host "  - Gemini KRX"
Write-Host "  - Groq"
Write-Host ""
Write-Host "Logs:"
Write-Host "  - logs\gemini_bot.log"
Write-Host "  - logs\groq_bot.log"
Write-Host ""
Write-Host "Claude is intentionally not started."
Write-Host "If you want paid Claude later:"
Write-Host '  $env:ALLOW_PAID_CLAUDE="true"'
Write-Host "  python stockmolt_bot_v6_1.py"
