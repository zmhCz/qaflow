Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Get-DevPaths {
    $root = Get-ProjectRoot
    return @{
        Root = $root
        Frontend = Join-Path $root 'frontend'
        Logs = Join-Path $root 'logs'
        Runtime = Join-Path $root '.runtime'
        Pids = Join-Path $root '.runtime\pids'
        RedisRoot = Join-Path $root '.runtime\redis'
        RedisDist = Join-Path $root '.runtime\redis\dist'
        RedisZip = Join-Path $root '.runtime\redis\redis-8.8.0.zip'
        RedisConfig = Join-Path $root 'scripts\redis.windows.dev.conf'
        Python = Join-Path $root 'venv\Scripts\python.exe'
        Daphne = Join-Path $root 'venv\Scripts\daphne.exe'
        Celery = Join-Path $root 'venv\Scripts\celery.exe'
    }
}

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Initialize-DevFolders {
    $paths = Get-DevPaths
    Ensure-Directory $paths.Logs
    Ensure-Directory $paths.Runtime
    Ensure-Directory $paths.Pids
    Ensure-Directory $paths.RedisRoot
}

function Get-PidFilePath {
    param([string]$Name)

    $paths = Get-DevPaths
    return Join-Path $paths.Pids "$Name.pid"
}

function Get-LogPaths {
    param([string]$Name)

    $paths = Get-DevPaths
    return @{
        Out = Join-Path $paths.Logs "$Name.out.log"
        Err = Join-Path $paths.Logs "$Name.err.log"
    }
}

function Get-ManagedProcess {
    param([string]$Name)

    $pidFile = Get-PidFilePath $Name
    if (-not (Test-Path $pidFile)) {
        return $null
    }

    $pidValue = (Get-Content -Path $pidFile -Raw).Trim()
    if (-not $pidValue) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    $process = Get-Process -Id ([int]$pidValue) -ErrorAction SilentlyContinue
    if (-not $process) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        return $null
    }

    return $process
}

function Save-ManagedProcessId {
    param(
        [string]$Name,
        [int]$Id
    )

    $pidFile = Get-PidFilePath $Name
    Set-Content -Path $pidFile -Value $Id -Encoding ascii
}

function Remove-ManagedProcessId {
    param([string]$Name)

    $pidFile = Get-PidFilePath $Name
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}

function Stop-ManagedProcess {
    param([string]$Name)

    $process = Get-ManagedProcess $Name
    if ($process) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    Remove-ManagedProcessId $Name
}

function Get-PortOwner {
    param([int]$Port)

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($connection) {
        return [int]$connection.OwningProcess
    }
    return $null
}

function Wait-ForTcpPort {
    param(
        [int]$Port,
        [int]$TimeoutSeconds = 20
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $owner = Get-PortOwner $Port
        if ($owner) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    return $false
}

function Clear-LogFiles {
    param([string]$Name)

    $logPaths = Get-LogPaths $Name
    foreach ($path in @($logPaths.Out, $logPaths.Err)) {
        if (Test-Path $path) {
            Remove-Item $path -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList,
        [string]$WorkingDirectory,
        [int]$Port = 0,
        [int]$WaitSeconds = 10
    )

    $existing = Get-ManagedProcess $Name
    if ($existing) {
        Write-Host "[$Name] already running with PID $($existing.Id)"
        return $existing
    }

    if ($Port -gt 0) {
        $portOwner = Get-PortOwner $Port
        if ($portOwner) {
            Write-Host "[$Name] skipped because port $Port is already in use by PID $portOwner"
            return $null
        }
    }

    Clear-LogFiles $Name
    $logPaths = Get-LogPaths $Name
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $logPaths.Out `
        -RedirectStandardError $logPaths.Err `
        -WindowStyle Hidden `
        -PassThru

    Save-ManagedProcessId -Name $Name -Id $process.Id

    if ($Port -gt 0) {
        if (-not (Wait-ForTcpPort -Port $Port -TimeoutSeconds $WaitSeconds)) {
            throw "[$Name] failed to open port $Port. Check $($logPaths.Err)"
        }
    } else {
        Start-Sleep -Seconds 2
        $check = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
        if (-not $check) {
            throw "[$Name] exited immediately. Check $($logPaths.Err)"
        }
    }

    return $process
}

function Get-RedisServerPath {
    $paths = Get-DevPaths
    if (-not (Test-Path $paths.RedisDist)) {
        return $null
    }

    $match = Get-ChildItem -Path $paths.RedisDist -Filter 'redis-server.exe' -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($match) {
        return $match.FullName
    }
    return $null
}

function Get-RedisCliPath {
    $paths = Get-DevPaths
    if (-not (Test-Path $paths.RedisDist)) {
        return $null
    }

    $match = Get-ChildItem -Path $paths.RedisDist -Filter 'redis-cli.exe' -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($match) {
        return $match.FullName
    }
    return $null
}

function Test-RedisReady {
    $cli = Get-RedisCliPath
    if (-not $cli) {
        return $false
    }

    try {
        $output = & $cli '-h' '127.0.0.1' '-p' '6379' 'PING' 2>$null
        return (($output | Out-String).Trim() -eq 'PONG')
    } catch {
        return $false
    }
}
