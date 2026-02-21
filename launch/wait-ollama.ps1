Write-Host "[START] モデルの生成確認" -ForegroundColor Green

$timeoutSeconds = 60
$intervalSeconds = 2
$elapsedSeconds = 0
$success = $false
$modelName = $env:MODEL_NAME

# 名前が設定されているかチェック
if ([string]::IsNullOrWhiteSpace($modelName)) {
    Write-Host "[!] 環境変数が設定されていません。" -ForegroundColor Red
    pause
    exit
}

# GGUFファイルが存在するかチェック
if (-not (Test-Path ".\models\*.gguf")) {
    Write-Host "[!] GGUFファイルが見つかりません。" -ForegroundColor Red
    pause
    exit
}

Write-Host "生成中..." -NoNewline -ForegroundColor Yellow

while ($elapsedSeconds -lt $timeoutSeconds) {
    $modelList = docker compose exec -T ollama ollama list 2>$null

    if ($modelList -like "*$modelName*") {
        $success = $true
        break
    }

    # 準備中の場合は待機
    Start-Sleep -s $intervalSeconds
    $elapsedSeconds += $intervalSeconds
    Write-Host "." -NoNewline -ForegroundColor Yellow
}

Write-Host ""

if (!$success) {
    Write-Host "[!] コンテナ内でのモデルの生成に失敗しました。" -ForegroundColor Red
    pause; exit
}

Write-Host "[END] モデルの生成確認" -ForegroundColor Green
