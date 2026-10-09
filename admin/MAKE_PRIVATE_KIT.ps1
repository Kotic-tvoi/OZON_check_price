# Runs locally on an administrator's Windows computer. Never upload the key to GitHub.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Join-Path $root 'OzonPrices'
if (!(Test-Path -LiteralPath (Join-Path $app 'OzonPrices.exe'))) {
    throw 'Распакуйте полный архив GitHub Actions: папка OzonPrices не найдена.'
}
Write-Host 'Сборка закрытого комплекта OzonPrices'
$keyPath = (Read-Host 'Полный путь к JSON-ключу сервисного аккаунта').Trim().Trim('"')
if (!(Test-Path -LiteralPath $keyPath -PathType Leaf)) { throw 'Файл ключа не найден.' }
$key = Get-Content -LiteralPath $keyPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($key.type -ne 'service_account' -or
    $key.client_email -ne 'sheets-server@fresh-forest-436813-i5.iam.gserviceaccount.com' -or
    !$key.private_key) { throw 'Это ключ другого сервисного аккаунта.' }
$url = (Read-Host 'URL Google Таблицы «Проверка цен»').Trim()
$match = [regex]::Match($url, '^https://docs\.google\.com/spreadsheets/d/([A-Za-z0-9_-]{20,})')
if (!$match.Success) { throw 'Нужен URL Google Таблицы вида https://docs.google.com/spreadsheets/d/.../edit' }
$id = $match.Groups[1].Value
$out = Join-Path $root 'OzonPrices_JKeratin_PRIVATE.zip'
if (Test-Path $out) { throw 'Закрытый ZIP уже существует; перенесите его перед повторной сборкой.' }
$temp = Join-Path ([IO.Path]::GetTempPath()) ('ozon_kit_' + [guid]::NewGuid().ToString('N'))
$target = Join-Path $temp 'OzonPrices'
try {
    New-Item -ItemType Directory $temp | Out-Null
    Copy-Item -LiteralPath $app -Destination $target -Recurse
    Copy-Item -LiteralPath $keyPath -Destination (Join-Path $target 'service-account.json')
    @{ spreadsheet_id = $id } | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $target 'config.local.json') -Encoding UTF8
    Set-Content -LiteralPath (Join-Path $target 'EXPORT_EXCEL.bat') -Encoding ASCII -Value @(
        '@echo off', 'cd /d "%~dp0"', 'OzonPrices.exe --excel-only', 'pause'
    )
    Compress-Archive -LiteralPath $target -DestinationPath $out -CompressionLevel Optimal
    Write-Host "Закрытый комплект: $out" -ForegroundColor Green
    Write-Host 'Передайте сотрудникам только через закрытый корпоративный канал.'
} finally {
    if (Test-Path $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
}
