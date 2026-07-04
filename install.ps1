# Media Compressor — установка на Windows (Docker).
# PowerShell: irm https://raw.githubusercontent.com/Lucem-afferens/media-compressor/main/install.ps1 | iex

$ErrorActionPreference = "Stop"
$Repo = "https://github.com/Lucem-afferens/media-compressor.git"
$InstallDir = if ($env:MEDIA_COMPRESSOR_DIR) { $env:MEDIA_COMPRESSOR_DIR } else { Join-Path $env:USERPROFILE "media-compressor" }
$Port = if ($env:MEDIA_COMPRESSOR_PORT) { $env:MEDIA_COMPRESSOR_PORT } else { "8090" }

Write-Host ""
Write-Host "  Media Compressor — установка (Windows)" -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Нужен Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $InstallDir "app.py"))) {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "Нужен Git: https://git-scm.com/download/win" -ForegroundColor Red
        exit 1
    }
    Write-Host "→ Клонирование в $InstallDir …"
    git clone --depth 1 $Repo $InstallDir
} else {
    Write-Host "→ Каталог уже есть: $InstallDir"
    Set-Location $InstallDir
    git pull --ff-only 2>$null
}

Set-Location $InstallDir
Write-Host "→ Запуск Docker…"
docker compose up -d --build

Write-Host ""
Write-Host "  Готово! Откройте: http://localhost:$Port" -ForegroundColor Green
Write-Host "  Остановить: docker compose down" -ForegroundColor DarkGray
Write-Host ""
