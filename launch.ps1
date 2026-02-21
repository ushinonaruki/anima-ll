# ============================================================
# Anima-LL フルオート起動スクリプト
#     実行コマンド: .\launch.ps1
#     文字コード  : UTF-8 with BOM
# ============================================================
$ErrorActionPreference = "Stop"

Write-Host "`n--- [Phase 1:] ---" -ForegroundColor Cyan
. .\launch\env.ps1

Write-Host "`n--- [Phase 2:] ---" -ForegroundColor Cyan
. .\launch\docker.ps1

Write-Host "`n--- [Phase 3:] ---" -ForegroundColor Cyan
. .\launch\python-check.ps1

Write-Host "`n--- [Phase 4:] ---" -ForegroundColor Cyan
. .\launch\python-sync.ps1

Write-Host "`n--- [Phase 5:] ---" -ForegroundColor Cyan
. .\launch\wait-ollama.ps1

Write-Host "`n--- [Anima-LL 覚醒] ---" -ForegroundColor Magenta
& python src/main.py
