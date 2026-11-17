#Requires -Version 5.1
<#
    ECHOES — updating an already installed player.
    Finds where ECHOES was installed (even if in a different folder),
    closes it, replaces the program files with new ones and updates
    bootloader yt-dlp. Playlists, library and settings are not affected.
#>
$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { $Host.UI.RawUI.WindowTitle = 'ECHOES — update' } catch {}
try { $Host.UI.RawUI.BackgroundColor = 'Black'; $Host.UI.RawUI.ForegroundColor = 'Gray' } catch {}
Clear-Host

$SRC_ROOT = Split-Path -Parent $PSScriptRoot
$SRC_APP = Join-Path $SRC_ROOT 'app'
. (Join-Path $PSScriptRoot 'launcher.ps1')
. (Join-Path $PSScriptRoot 'player.ps1')

function Ok([string]$t)   { Write-Host "      √ $t" -ForegroundColor Green }
function Info([string]$t) { Write-Host "      · $t" -ForegroundColor DarkGray }
function Warn([string]$t) { Write-Host "      ! $t" -ForegroundColor Yellow }
function Step([string]$t) { Write-Host ''; Write-Host "  » $t" -ForegroundColor White }
function Done([int]$code) {
    Write-Host ''
    Read-Host '  Click Enter, to close' | Out-Null
    exit $code
}
function Fail([string]$msg) {
    Write-Host ''
    Write-Host "  × $msg" -ForegroundColor Red
    Done 1
}

Write-Host ''
Write-Host '   ███████╗ ██████╗██╗  ██╗ ██████╗ ███████╗███████╗' -ForegroundColor Yellow
Write-Host '   ██╔════╝██╔════╝██║  ██║██╔═══██╗██╔════╝██╔════╝' -ForegroundColor Yellow
Write-Host '   █████╗  ██║     ███████║██║   ██║█████╗  ███████╗' -ForegroundColor DarkYellow
Write-Host '   ███████╗╚██████╗██║  ██║╚██████╔╝███████╗███████║' -ForegroundColor DarkYellow
Write-Host '   ╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝' -ForegroundColor DarkGray
Write-Host '                     update' -ForegroundColor Gray

if (-not (Test-Path (Join-Path $SRC_APP 'main.py'))) {
    Fail 'The app folder is missing. Extract the entire download and run the updater from that folder.'
}

# ── 1. where installed ECHOES ─────────────────────────────────────────────
Step 'Looking for installed ECHOES'
$cands = New-Object System.Collections.Generic.List[string]
try {
    $loc = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ECHOES' -ErrorAction Stop).InstallLocation
    if ($loc) { $cands.Add($loc) }
} catch {}
try {
    $ws = New-Object -ComObject WScript.Shell
    foreach ($lnk in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'ECHOES.lnk'),
                       (Join-Path ([Environment]::GetFolderPath('Programs')) 'ECHOES\ECHOES.lnk'))) {
        if (Test-Path $lnk) {
            $t = $ws.CreateShortcut($lnk).TargetPath            # ...\ECHOES\python\Echoes.exe (or legacy pythonw.exe)
            if ($t) { $cands.Add((Split-Path -Parent (Split-Path -Parent $t))) }
        }
    }
} catch {}
$cands.Add((Join-Path $env:LOCALAPPDATA 'Programs\ECHOES'))
$InstallDir = $null
foreach ($c in $cands) {
    if ($c -and (Test-Path (Join-Path $c 'app\main.py')) -and (Test-Path (Join-Path $c 'python\python.exe'))) {
        $InstallDir = $c; break
    }
}
if (-not $InstallDir) {
    Fail 'ECHOES not found on this computer. First install it: »INSTALL ECHOES.bat».'
}
$APP = Join-Path $InstallDir 'app'
$PY  = Join-Path $InstallDir 'python\python.exe'
Ok "found: $InstallDir"
$launcherSource = Get-EchoesLauncher $SRC_ROOT

$verFile = Join-Path $APP 'version.txt'
$oldVer = if (Test-Path $verFile) { (Get-Content $verFile -Raw).Trim() } else { 'old' }
$newVerFile = Join-Path $SRC_APP 'version.txt'
$newVer = if (Test-Path $newVerFile) { (Get-Content $newVerFile -Raw).Trim() } else { 'new' }
Info "version: $oldVer  →  $newVer"

# ── 2. close the player ─────────────────────────────────────────────────────
Step 'I′m closing ECHOES, if it′s open'
$killed = Stop-EchoesRuntime $InstallDir -IncludeExternal
if ($killed) { Ok 'closed' } else { Ok 'was not launched' }
$player = Install-EchoesPlayer $InstallDir

# ── 3. replace files ────────────────────────────────────────────────────
Step 'Updating program files'
Get-ChildItem -Path $APP -Filter '*.dll.old*' -File -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue }
$changed = 0; $same = 0; $failed = @()
Get-ChildItem -Path $SRC_APP -File | ForEach-Object {
    $dst = Join-Path $APP $_.Name
    $need = $true
    if (Test-Path $dst) {
        try {
            $need = (Get-FileHash $_.FullName -Algorithm MD5).Hash -ne (Get-FileHash $dst -Algorithm MD5).Hash
        } catch { $need = $true }
    }
    if ($need) {
        $ok = $false
        for ($i = 0; $i -lt 5 -and -not $ok; $i++) {
            try { Copy-Item $_.FullName -Destination $dst -Force; $ok = $true }
            catch { Start-Sleep -Milliseconds 600 }
        }
        if (-not $ok -and $_.Extension -eq '.dll' -and (Test-Path $dst)) {
            # busy DLL (C++-effects core) Windows Doesn′t allow you to overwrite, but allows you to rename:
            # the old one goes to the side and is deleted during the next update
            try {
                Rename-Item $dst ($_.Name + '.old' + (Get-Random)) -Force
                Copy-Item $_.FullName -Destination $dst -Force
                $ok = $true
            } catch {}
        }
        if ($ok) { $changed++; Info "updated $($_.Name)" } else { $failed += $_.Name }
    } else { $same++ }
}
foreach ($assetFolder in @('assets', 'discord_assets', 'dsl_themes', 'montage_native', 'sounds')) {
    $assetSource = Join-Path $SRC_APP $assetFolder
    if (Test-Path -LiteralPath $assetSource) {
        $assetTarget = Join-Path $APP $assetFolder
        New-Item -ItemType Directory -Path $assetTarget -Force | Out-Null
        Get-ChildItem -LiteralPath $assetSource | Copy-Item -Destination $assetTarget -Recurse -Force
    }
}
Get-ChildItem -Path $APP -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
Remove-Item (Join-Path $APP '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
$un = Join-Path $PSScriptRoot 'uninstall.en.ps1'
if (Test-Path $un) { Copy-Item $un -Destination (Join-Path $InstallDir 'uninstall.ps1') -Force -ErrorAction SilentlyContinue }
if ($failed.Count) {
    Fail "Failed to replace: $($failed -join ', '). Close ECHOES, including its tray icon, and run the updater again."
}
Ok "updated files: $changed, no changes: $same"

# ── 4. loader and libraries ────────────────────────────────────────────
Step 'Updating the bootloader yt-dlp and search YouTube Music (1-2 minutes)'
$old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
& $PY -m pip install --upgrade --prefer-binary --no-warn-script-location --disable-pip-version-check `
      --timeout 60 --retries 3 yt-dlp ytmusicapi syncedlyrics requests mutagen Pillow sounddevice pycryptodomex websockets av `
      winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Media `
      winrt-Windows.Media.Playback winrt-Windows.Storage winrt-Windows.Storage.Streams 2>&1 | ForEach-Object {
    $l = "$_"
    if ($l -match '^Successfully installed (.+)') { Info "updated: $($Matches[1])" }
}
$pipCode = $LASTEXITCODE
$ErrorActionPreference = $old
if ($pipCode -eq 0) { Ok 'done' } else { Warn 'some libraries have not been updated (no internet?) - the player is still updated' }

if ($launcherSource) { Install-EchoesLauncher $launcherSource $InstallDir }
try { Update-EchoesWindowsShortcuts $InstallDir }
catch { Warn "Could not refresh shortcuts: $($_.Exception.Message)" }

# ── done ───────────────────────────────────────────────────────────────
try {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ECHOES'
    if ((Test-Path $key) -and (Get-ItemProperty -Path $key).InstallLocation -eq $InstallDir) {
        Set-ItemProperty -Path $key -Name DisplayVersion -Value $newVer -ErrorAction SilentlyContinue
        Set-ItemProperty -Path $key -Name DisplayIcon -Value "$player,0" -ErrorAction SilentlyContinue
    }
} catch {}
Write-Host ''
Write-Host '  ╔══════════════════════════════════════════════╗' -ForegroundColor Green
Write-Host "  ║   ECHOES UPDATED  ·  version $($newVer.PadRight(16))║" -ForegroundColor Green
Write-Host '  ╚══════════════════════════════════════════════╝' -ForegroundColor Green
Write-Host ''
$go = Read-Host '   Start ECHOES? [Enter — yes / n — no]'
if ($go -notmatch '^(n|n|no|no)$') {
    Start-Process -FilePath $player -ArgumentList "`"$(Join-Path $APP 'main.py')`"" -WorkingDirectory $APP
}
exit 0
