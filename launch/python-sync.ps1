Write-Host "[START] Pythonライブラリの同期" -ForegroundColor Green

& python -m pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] ライブラリのインストールに失敗しました。" -ForegroundColor Red
    pause
    exit
}

Write-Host "[END] Pythonライブラリの同期" -ForegroundColor Green
