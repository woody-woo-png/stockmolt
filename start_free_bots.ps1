$ErrorActionPreference = "Stop"

$root = "C:\Users\amire\AI\stockmolt"
$python = "C:\Users\amire\AppData\Local\Programs\Python\Python312\python.exe"
$logDir = Join-Path $root "logs"
$scripts = @("Gemini_krx_bot_v2.py", "stockmolt_bot_groq.py", "stockmolt_bot_openrouter.py")

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

# 기존 봇 프로세스 종료
Write-Host "기존 봇 종료 중..."
$killed = 0
foreach ($proc in Get-Process python* -ErrorAction SilentlyContinue) {
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
        foreach ($script in $scripts) {
            if ($cmdline -like "*$script*") {
                Stop-Process -Id $proc.Id -Force
                Write-Host "  종료: $script (PID $($proc.Id))"
                $killed++
                break
            }
        }
    } catch {}
}
if ($killed -eq 0) { Write-Host "  실행 중인 봇 없음" }
Start-Sleep -Seconds 2

function Start-Bot {
    param(
        [string]$ScriptName,
        [string]$LogName
    )

    $scriptPath = Join-Path $root $ScriptName
    $outLog = Join-Path $logDir $LogName
    $errLog = Join-Path $logDir ($LogName -replace '\.log$', '_err.log')

    Start-Process `
        -FilePath $python `
        -ArgumentList @("-u", $scriptPath) `
        -WorkingDirectory $root `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden
}

Start-Bot -ScriptName "Gemini_krx_bot_v2.py"          -LogName "gemini_bot.log"
Start-Bot -ScriptName "stockmolt_bot_groq.py"          -LogName "groq_bot.log"
Start-Bot -ScriptName "stockmolt_bot_openrouter.py"    -LogName "openrouter_bot.log"

Write-Host "봇 시작 완료:"
Write-Host "  - Gemini KRX        (logs\gemini_bot.log)"
Write-Host "  - Groq              (logs\groq_bot.log)"
Write-Host "  - OpenRouter        (logs\openrouter_bot.log)"
