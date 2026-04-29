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

Start-Bot -ScriptName "Gemini_krx_bot_v2.py"          -LogName "gemini_bot.log"
Start-Bot -ScriptName "Stockmolt bot groq.py"          -LogName "groq_bot.log"
Start-Bot -ScriptName "stockmolt_bot_openrouter.py"    -LogName "openrouter_bot.log"

Write-Host "Started bots:"
Write-Host "  - Gemini KRX        (logs\gemini_bot.log)"
Write-Host "  - Groq              (logs\groq_bot.log)"
Write-Host "  - OpenRouter        (logs\openrouter_bot.log)"
Write-Host ""
Write-Host "필요한 환경변수 (.env):"
Write-Host "  OPENROUTER_API_KEY=..."
