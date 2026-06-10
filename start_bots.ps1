$root   = "C:\Users\amire\AI\stockmolt"
$python = "C:\Users\amire\AppData\Local\Programs\Python\Python312\python.exe"
$logDir = Join-Path $root "logs"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"

# 기존 StockMolt 봇 프로세스 종료 (중복 실행·이중 포스팅 방지)
$botScripts = @("stockmolt_bot_groq.py", "stockmolt_bot_openrouter.py", "stockmolt_bot_deepseek.py", "stockmolt_bot_gemini.py")
foreach ($proc in Get-Process python* -ErrorAction SilentlyContinue) {
    try {
        $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.Id)").CommandLine
        foreach ($s in $botScripts) {
            if ($cmdline -like "*$s*") {
                Stop-Process -Id $proc.Id -Force
                Write-Host "  기존 종료: $s (PID $($proc.Id))"
                break
            }
        }
    } catch {}
}
Start-Sleep -Seconds 2

function Start-BotWithDelay {
    param([string]$Script, [string]$Log, [int]$DelayMinutes = 0)
    $args = "`"$(Join-Path $root $Script)`""
    if ($DelayMinutes -gt 0) { $args += " --delay-minutes $DelayMinutes" }
    $logPath = Join-Path $logDir $Log
    $errPath = Join-Path $logDir ($Log -replace "\.log$", ".err.log")
    $proc = Start-Process `
        -FilePath $python `
        -ArgumentList $args `
        -WorkingDirectory $root `
        -RedirectStandardOutput $logPath `
        -RedirectStandardError  $errPath `
        -WindowStyle Hidden `
        -PassThru
    $tag = if ($DelayMinutes -gt 0) { "(${DelayMinutes}분 후 첫 실행)" } else { "" }
    Write-Host "  ✅ $Script (PID: $($proc.Id)) $tag"
    return $proc
}

Write-Host "StockMolt 봇 시작 중... (15분 간격 분산)"
$g = Start-BotWithDelay -Script "stockmolt_bot_groq.py"       -Log "groq_bot.log"       -DelayMinutes 0
$o = Start-BotWithDelay -Script "stockmolt_bot_openrouter.py" -Log "openrouter_bot.log" -DelayMinutes 15
$d = Start-BotWithDelay -Script "stockmolt_bot_deepseek.py"   -Log "deepseek_bot.log"  -DelayMinutes 30
$m = Start-BotWithDelay -Script "stockmolt_bot_gemini.py"     -Log "gemini_bot.log"    -DelayMinutes 45
Write-Host ""
Write-Host "실행 중: Groq=$($g.Id) / OpenRouter=$($o.Id) / DeepSeek=$($d.Id) / Gemini=$($m.Id)"
Write-Host "포스팅 시간: Groq=:00 / OpenRouter=:15 / DeepSeek=:30 / Gemini=:45"
Write-Host "로그: logs\ 폴더 확인"
