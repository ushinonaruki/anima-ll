Write-Host "[START] Python環境の準備" -ForegroundColor Green

if (-not (Get-Command "python" -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Pythonが見つかりません。wingetでインストールを開始します..." -ForegroundColor Yellow
    winget install -e --id Python.Python.3.11
    
    Write-Host "[!] インストールが完了しました。一度このウィンドウを閉じ、再度実行してください。" -ForegroundColor Yellow
    pause
    exit
}

Write-Host "[END] Python環境の準備" -ForegroundColor Green
