Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'dev-common.ps1')

Initialize-DevFolders

$items = @(
    @{ Name = 'redis'; Port = 6379 },
    @{ Name = 'backend'; Port = 8001 },
    @{ Name = 'frontend'; Port = 3000 },
    @{ Name = 'celery'; Port = 0 }
)

foreach ($item in $items) {
    $process = Get-ManagedProcess $item.Name
    $pidValue = if ($process) { $process.Id } else { '-' }
    $portValue = if ($item.Port -gt 0) { (Get-PortOwner $item.Port) } else { '-' }
    $portState = if ($item.Port -gt 0) {
        if ($portValue) { "listen:$($item.Port)" } else { 'not-listening' }
    } else {
        if ($process) { 'running' } else { 'stopped' }
    }

    Write-Host ("{0,-8} pid={1,-8} state={2}" -f $item.Name, $pidValue, $portState)
}

Write-Host ''
Write-Host 'Logs:'
Write-Host "  $((Join-Path (Get-DevPaths).Logs 'redis.out.log'))"
Write-Host "  $((Join-Path (Get-DevPaths).Logs 'backend.out.log'))"
Write-Host "  $((Join-Path (Get-DevPaths).Logs 'celery.out.log'))"
Write-Host "  $((Join-Path (Get-DevPaths).Logs 'frontend.out.log'))"
