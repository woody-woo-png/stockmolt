$ErrorActionPreference = "SilentlyContinue"

$targets = @(
    "Gemini_krx_bot_v2.py",
    "Stockmolt bot groq.py",
    "stockmolt_bot_v6_1.py"
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
                    Id = $proc.Id
                    Script = $target
                }
                break
            }
        }
    } catch {
    }
}

if ($stopped.Count -eq 0) {
    Write-Host "No bot processes were found."
} else {
    Write-Host "Stopped bot processes:"
    $stopped | Sort-Object Id | Format-Table -AutoSize
}
