Write-Host "[START] Dockerの準備" -ForegroundColor Green

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

Write-Host "[END] Dockerの準備" -ForegroundColor Green
