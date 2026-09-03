param(
    [switch]$SkipRedis,
    [switch]$SkipBackend,
    [switch]$SkipCelery,
    [switch]$SkipFrontend
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'dev-common.ps1')

$paths = Get-DevPaths
Initialize-DevFolders

Write-Host '[static] collecting static files...'
& $paths.Python manage.py collectstatic --noinput | Out-Null
Write-Host '[static] collectstatic finished'

function Ensure-RedisPrepared {
    $redisServer = Get-RedisServerPath
    if ($redisServer) {
        return $redisServer
    }

    Write-Host 'Redis runtime is missing. Running setup-redis.ps1...'
    & (Join-Path $PSScriptRoot 'setup-redis.ps1')
    $redisServer = Get-RedisServerPath
    if (-not $redisServer) {
        throw 'Redis runtime setup failed.'
    }
    return $redisServer
}

if (-not $SkipRedis) {
    $redisServer = Ensure-RedisPrepared
    $redisProcess = Get-ManagedProcess 'redis'
    if ($redisProcess -or (Test-RedisReady)) {
        if ($redisProcess) {
            Write-Host "[redis] already running with PID $($redisProcess.Id)"
        } else {
            Write-Host '[redis] already reachable on 127.0.0.1:6379'
        }
    } else {
        $redisWorkingDir = Split-Path $redisServer -Parent
        $runtimeRedisConfig = Join-Path $redisWorkingDir 'redis.windows.dev.conf'
        Copy-Item -Path $paths.RedisConfig -Destination $runtimeRedisConfig -Force
        Start-ManagedProcess -Name 'redis' -FilePath $redisServer -ArgumentList @('redis.windows.dev.conf') -WorkingDirectory $redisWorkingDir -Port 6379 -WaitSeconds 15 | Out-Null
        if (-not (Test-RedisReady)) {
            throw '[redis] process started but PING failed.'
        }
        Write-Host '[redis] started on 127.0.0.1:6379'
    }
}

if (-not $SkipBackend) {
    Start-ManagedProcess -Name 'backend' -FilePath $paths.Daphne -ArgumentList @('-b', '127.0.0.1', '-p', '8001', 'backend.asgi:application') -WorkingDirectory $paths.Root -Port 8001 -WaitSeconds 15 | Out-Null
    Write-Host '[backend] started on http://127.0.0.1:8001'
}

if (-not $SkipCelery) {
    Start-ManagedProcess -Name 'celery' -FilePath $paths.Celery -ArgumentList @('-A', 'backend', 'worker', '-l', 'info', '-P', 'solo', '--concurrency=1') -WorkingDirectory $paths.Root | Out-Null
    Write-Host '[celery] started'
}

if (-not $SkipFrontend) {
    Start-ManagedProcess -Name 'frontend' -FilePath 'cmd.exe' -ArgumentList @('/c', 'npm run dev -- --host 127.0.0.1 --port 3000') -WorkingDirectory $paths.Frontend -Port 3000 -WaitSeconds 20 | Out-Null
    Write-Host '[frontend] started on http://127.0.0.1:3000'
}

Write-Host ''
Write-Host 'Ready:'
Write-Host '  Frontend: http://127.0.0.1:3000'
Write-Host '  Backend : http://127.0.0.1:8001'
Write-Host '  Docs    : http://127.0.0.1:8001/api/docs/'
Write-Host '  Admin   : http://127.0.0.1:8001/admin/'
