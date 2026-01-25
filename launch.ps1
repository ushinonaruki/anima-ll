# ============================================================
# Anima-LL フルオート起動スクリプト
#     実行コマンド: .\launch.ps1
#     文字コード  : UTF-8 with BOM
# ============================================================
$ErrorActionPreference = "Stop"

# --- [.env] ファイルを読み込んで環境変数にセットする ---
Write-Host "`n--- [Phase 0: 環境変数の読み込み] ---" -ForegroundColor Cyan
if (Test-Path ".env") {
    Get-Content .env | Where-Object { $_ -and -not $_.StartsWith("#") } | ForEach-Object {
        $name, $value = $_.Split('=', 2)
        [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
    }
}
else {
    Write-Host "[!] 環境変数が見つかりません。" -ForegroundColor Red
    pause; exit
}
Write-Host "[OK] 環境変数が読み込まれました。" -ForegroundColor Green

Write-Host "`n--- [Phase 1: Dockerの準備] ---" -ForegroundColor Cyan
& {
    $ErrorActionPreference = "Continue"
    docker info > $null 2>&1
}
if ($LASTEXITCODE -eq 0) {
    & {
        $ErrorActionPreference = "Continue"
        docker compose up -d --build
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[!] docker compose up に失敗しました。設定ファイルを確認してください。" -ForegroundColor Red
        pause; exit
    }
}
else {
    Write-Host "[!] Dockerエンジンが応答しません。Docker Desktopが起動しているか確認してください。" -ForegroundColor Red
    pause; exit
}
Write-Host "[OK] Dockerコンテナが正常に動作しています。" -ForegroundColor Green

Write-Host "`n--- [Phase 2: Python環境の準備] ---" -ForegroundColor Cyan
try {
    $pythonCmd = "python"
    python --version > $null 2>&1
}
catch {
    try {
        # pythonで見つからない場合、pyコマンドを試す（Windows標準のランチャー）
        py --version > $null 2>&1
        $pythonCmd = "py"
    }
    catch {
        Write-Host "[!] Pythonが見つかりません。wingetでインストールを開始します..." -ForegroundColor Yellow
        winget install -e --id Python.Python.3.11
        Write-Host "[!] インストールが完了しました。一度このウィンドウを閉じ、再度実行してください。" -ForegroundColor Cyan
        pause; exit
    }
}
Write-Host "[OK] Python環境を確認しました: $($pythonCmd)" -ForegroundColor Green

Write-Host "`n--- [Phase 3: ライブラリの同期] ---" -ForegroundColor Cyan
try {
    & $pythonCmd -m pip install -r requirements.txt
}
catch {
    Write-Host "[!] ライブラリのインストールに失敗しました。" -ForegroundColor Red
    pause; exit
}
Write-Host "[OK] ライブラリは最新です。" -ForegroundColor Green

Write-Host "`n--- [Phase 4: モデルの生成確認] ---" -ForegroundColor Cyan
$timeoutSeconds = 60
$intervalSeconds = 2
$elapsedSeconds = 0
$success = $false
$modelName = $env:MODEL_NAME
Write-Host "生成中..." -ForegroundColor Yellow
while ($elapsedSeconds -lt $timeoutSeconds) {
    $modelList = docker compose exec -T ollama ollama list 2>$null

    if ($modelList -like "*$modelName*") {
        $success = $true
        break
    }

    # 準備中の場合は待機
    Start-Sleep -s $intervalSeconds
    $elapsedSeconds += $intervalSeconds
    Write-Host "." -NoNewline
}
Write-Host ""
if (!$success) {
    Write-Host "[!] コンテナ内でのモデルの生成に失敗しました。" -ForegroundColor Red
    pause; exit
}
Write-Host "[OK] コンテナ内でのモデルの生成が完了しました。" -ForegroundColor Green

Write-Host "`n--- [Phase 5: Fish Speech起動確認] ---" -ForegroundColor Cyan
$fishTimeoutSeconds = 600
$fishIntervalSeconds = 5
$fishElapsedSeconds = 0
$fishSuccess = $false
Write-Host "起動中..." -ForegroundColor Yellow
while ($fishElapsedSeconds -lt $fishTimeoutSeconds) {
    $fishLogs = docker compose logs fish_speech 2>$null
    
    if ($fishLogs -like "*Application startup complete.*") {
        $fishSuccess = $true
        break
    }
    
    # 起動中の場合は待機
    Start-Sleep -s $fishIntervalSeconds
    $fishElapsedSeconds += $fishIntervalSeconds
    Write-Host "." -NoNewline
}
Write-Host ""
if (!$fishSuccess) {
    Write-Host "[!] Fish Speechの起動に失敗しました。" -ForegroundColor Red
    pause; exit
}
Write-Host "[OK] Fish Speechの起動が完了しました。" -ForegroundColor Green

Write-Host "`n--- [Final: Anima-LL 覚醒] ---" -ForegroundColor Magenta
& $pythonCmd src/main.py
pause
