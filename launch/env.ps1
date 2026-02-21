Write-Host "[START] 環境変数の読み込み" -ForegroundColor Green

if (Test-Path ".env") {
    Get-Content .env | Where-Object { $_ -and -not $_.StartsWith("#") } | ForEach-Object {
        $name, $value = $_.Split('=', 2)
        [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), "Process")
    }
}
else {
    Write-Host "[!] 環境変数が見つかりません" -ForegroundColor Red
    pause; exit
}

Write-Host "[END] 環境変数の読み込み" -ForegroundColor Green
