$ErrorActionPreference = "Stop"

$repo = "CharTyr/STS2-Agent"
$target = Join-Path $PSScriptRoot "vendor"
New-Item -ItemType Directory -Force -Path $target | Out-Null

$release = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
$asset = $release.assets | Where-Object {
    $_.name -match '\.(zip|7z)$'
} | Select-Object -First 1

if (-not $asset) {
    throw "No zip/7z release asset found for $repo latest release."
}

$outFile = Join-Path $target $asset.name
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $outFile

Write-Host "Downloaded $($asset.name) to $outFile"
Write-Host "Extract it and copy STS2AIAgent.dll, STS2AIAgent.pck, and mod_id.json into the game's mods directory."
