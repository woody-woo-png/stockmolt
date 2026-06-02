$ErrorActionPreference = "SilentlyContinue"

$targets = @(
    "stockmolt_bot_gemini.py",
    "stockmolt_bot_groq.py",
    "stockmolt_bot_openrouter.py",
    "stockmolt_bot_deepseek.py"
)

$stopped = @()

Get-Process python | ForEach-Object {
    try {
        $proc = $_
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)").CommandLine
        foreach ($target in $targets) {
            if ($cmd -like "*$target*") {
                Stop-Process -Id $proc.Id -Force
                $stopped += [PSCustomObject]@{
                    Id     = $proc.Id
                    Script = $target
                }
                break
            }
        }
    } catch {}
}

if ($stopped.Count -eq 0) {
    Write-Host "실행 중인 봇이 없습니다."
} else {
    Write-Host "종료된 봇:"
    $stopped | Sort-Object Id | Format-Table -AutoSize
}
