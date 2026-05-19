$root   = "C:\Users\amire\AI\stockmolt"
$python = "C:\Users\amire\AppData\Local\Programs\Python\Python312\python.exe"
$logDir = Join-Path $root "logs"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

function Start-Bot {
    param([string]$Script, [string]$Log)
    $logPath  = Join-Path $logDir $Log
    $errPath  = Join-Path $logDir ($Log -replace "\.log$", ".err.log")
    $proc = Start-Process `
        -FilePath $python `
        -ArgumentList "`"$(Join-Path $root $Script)`"" `
        -WorkingDirectory $root `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError  $errPath `
        -WindowStyle Hidden `
        -PassThru
    Write-Host "  ✅ $Script (PID: $($proc.Id))"
    return $proc
}

Write-Host "StockMolt 봇 시작 중..."
$g = Start-Bot -Script "stockmolt_bot_groq.py"   -Log "groq_bot.log"
$m = Start-Bot -Script "stockmolt_bot_gemini.py" -Log "gemini_bot.log"
Write-Host ""
Write-Host "실행 중: Groq PID=$($g.Id) / Gemini PID=$($m.Id)"
Write-Host "로그: logs\groq_bot.log / logs\gemini_bot.log"
