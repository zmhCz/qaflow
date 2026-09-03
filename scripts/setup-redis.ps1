Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'dev-common.ps1')

$paths = Get-DevPaths
Initialize-DevFolders
Ensure-Directory $paths.RedisDist

$redisServer = Get-RedisServerPath
if ($redisServer) {
    Write-Host "Redis already prepared at $redisServer"
    exit 0
}

$url = 'https://github.com/taizod1024/redis-windows-fork/releases/download/8.8.0/Redis-8.8.0-Windows-x64-msys2.zip'
if (-not (Test-Path $paths.RedisZip) -or ((Get-Item $paths.RedisZip).Length -le 0)) {
    Write-Host "Downloading Redis portable package..."
    curl.exe -L $url -o $paths.RedisZip
    if ($LASTEXITCODE -ne 0) {
        throw "Redis download failed."
    }
}

Write-Host "Extracting Redis package..."
Expand-Archive -Path $paths.RedisZip -DestinationPath $paths.RedisDist -Force

$redisServer = Get-RedisServerPath
if (-not $redisServer) {
    throw 'redis-server.exe was not found after extraction.'
}

Write-Host "Redis prepared at $redisServer"
