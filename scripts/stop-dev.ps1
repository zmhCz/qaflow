Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'dev-common.ps1')

foreach ($name in @('frontend', 'celery', 'backend', 'redis')) {
    Stop-ManagedProcess $name
    Write-Host "[$name] stopped"
}
