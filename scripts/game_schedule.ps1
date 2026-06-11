# scripts/game_schedule.ps1
# 게임 일일 트리거. Windows 작업 스케줄러에 2개 등록 권장:
#   - 풀 생성: US 장 마감 직후 (한국시간 평일 06:10 KST 경 = 미 동부 16:10 ET 후)
#   - 판정:    다음 US 장 마감 직후 (다음 평일 06:10 KST)
param([ValidateSet("pool","resolve")] [string]$Action)
$BASE = "https://oyatbvqpilvbhqpiafwp.supabase.co/functions/v1"
$ANON = $env:SUPABASE_ANON_KEY
if (-not $ANON) { Write-Error "SUPABASE_ANON_KEY 환경변수 필요"; exit 1 }
$headers = @{ "apikey" = $ANON; "Authorization" = "Bearer $ANON" }
$fn = if ($Action -eq "pool") { "game-generate-pool" } else { "game-resolve" }
$resp = Invoke-RestMethod -Method Post -Uri "$BASE/$fn" -Headers $headers
$resp | ConvertTo-Json -Depth 5
