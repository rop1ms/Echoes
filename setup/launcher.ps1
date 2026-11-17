# launcher.sha256 is inside the signed release tree. Older updaters also verify it.
param([string]$ApplyTo)

function Get-EchoesLauncher([string]$SourceRoot) {
    $source = Join-Path $SourceRoot 'ECHOES Launcher.exe'
    $checksum = Join-Path $SourceRoot 'setup\launcher.sha256'
    if (-not (Test-Path -LiteralPath $checksum -PathType Leaf)) { return $null }
    $expected = (Get-Content -LiteralPath $checksum -Raw).Trim()
    if ($expected -notmatch '^[a-f0-9]{64}$' -or
        -not (Test-Path -LiteralPath $source -PathType Leaf) -or
        (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expected) {
        throw 'ECHOES Launcher.exe: SHA-256 verification failed.'
    }
    return $source
}

function Copy-EchoesExecutable([string]$Source, [string]$Target) {
    if ($Source -eq $target) { return }
    $stage = Join-Path (Split-Path -Parent $target) ("echoes-" + [Guid]::NewGuid() + ".tmp")
    $backup = "$stage.bak"
    try {
        [IO.File]::Copy($Source, $stage)
        if (Test-Path -LiteralPath $target) {
            [IO.File]::Replace($stage, $target, $backup)
        } else {
            [IO.File]::Move($stage, $target)
        }
    } finally {
        Remove-Item -LiteralPath $stage, $backup -Force -ErrorAction SilentlyContinue
    }
}

function Copy-EchoesLauncher([string]$Source, [string]$InstallDir) {
    Copy-EchoesExecutable $Source (Join-Path $InstallDir 'ECHOES Launcher.exe')
}

function Install-EchoesLauncher([string]$Source, [string]$InstallDir) {
    if (-not $Source) { return }
    try {
        Copy-EchoesLauncher $Source $InstallDir
    } catch {
        # A launcher that started setup may hold its own EXE open until the window closes.
        $helper = Join-Path (Split-Path -Parent $Source) 'setup\launcher.ps1'
        $powershell = Join-Path $PSHOME 'powershell.exe'
        Start-Process -FilePath $powershell -WindowStyle Hidden -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $helper),
            '-ApplyTo', ('"{0}"' -f $InstallDir)
        )
    }
}

if ($ApplyTo) {
    $ErrorActionPreference = 'Stop'
    $packageRoot = Split-Path -Parent $PSScriptRoot
    $source = Get-EchoesLauncher $packageRoot
    if (-not $source) { exit 1 }
    $version = (Get-Content -LiteralPath (Join-Path $packageRoot 'app\version.txt') -Raw).Trim()
    $installedVersion = Join-Path $ApplyTo 'app\version.txt'
    $deadline = [DateTime]::UtcNow.AddMinutes(5)
    do {
        if ((Get-Content -LiteralPath $installedVersion -Raw).Trim() -ne $version) { exit 1 }
        try {
            Copy-EchoesLauncher $source $ApplyTo
            exit 0
        } catch {
            Start-Sleep -Seconds 1
        }
    } while ([DateTime]::UtcNow -lt $deadline)
    exit 1
}
