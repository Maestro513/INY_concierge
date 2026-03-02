# Upload extracted JSON files to Render persistent disk (Windows PowerShell)
#
# Usage:
#   $env:ADMIN_SECRET = "your_secret"
#   .\upload_extracted.ps1
#

param(
    [string]$RenderUrl = "https://iny-concierge.onrender.com"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExtractedDir = Join-Path $ScriptDir "extracted"
$Tarball = Join-Path $env:TEMP "extracted_jsons.tar.gz"

if (-not $env:ADMIN_SECRET) {
    Write-Host "ERROR: Set ADMIN_SECRET environment variable first." -ForegroundColor Red
    Write-Host '  $env:ADMIN_SECRET = "your_render_admin_secret"'
    exit 1
}

if (-not (Test-Path $ExtractedDir)) {
    Write-Host "ERROR: extracted/ directory not found at $ExtractedDir" -ForegroundColor Red
    exit 1
}

$jsonFiles = Get-ChildItem -Path $ExtractedDir -Filter "*.json"
$count = $jsonFiles.Count
Write-Host "=== Extracted JSON Upload ===" -ForegroundColor Cyan
Write-Host "  Directory: $ExtractedDir"
Write-Host "  JSON files: $count"
Write-Host "  Target: $RenderUrl/api/admin/upload/extracted"
Write-Host ""

# Compress using tar (available on Windows 10+)
Write-Host "Compressing $count JSON files..."
Push-Location $ExtractedDir
tar czf $Tarball .
Pop-Location
$size = [math]::Round((Get-Item $Tarball).Length / 1MB, 1)
Write-Host "  Archive: $Tarball ($size MB)"
Write-Host ""

# Upload using curl
Write-Host "Uploading to Render (this may take a few minutes)..."
$uploadUrl = "$RenderUrl/api/admin/upload/extracted"

$result = curl.exe -s -w "`n%{http_code}" `
    -X POST $uploadUrl `
    -H "X-Admin-Secret: $($env:ADMIN_SECRET)" `
    -F "file=@$Tarball" `
    --max-time 600

$lines = $result -split "`n"
$httpCode = $lines[-1]
$body = ($lines[0..($lines.Length - 2)]) -join "`n"

Write-Host ""
if ($httpCode -eq "200") {
    Write-Host "SUCCESS!" -ForegroundColor Green
    Write-Host $body
} else {
    Write-Host "FAILED (HTTP $httpCode)" -ForegroundColor Red
    Write-Host $body
    Remove-Item -Force $Tarball -ErrorAction SilentlyContinue
    exit 1
}

# Cleanup
Remove-Item -Force $Tarball -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "Done. Extracted JSONs are now on Render disk." -ForegroundColor Green
