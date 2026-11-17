#Requires -Version 5.1
<#
    ECHOES — installer for Windows 10/11 (64-bit).
    Installs EVERYTHING yourself, without administrator rights:
      * private embedded Python, independent of other Python installations
      * all libraries Python (PyQt6, numpy, yt-dlp, ...)
      * VLC (playback engine) and ffmpeg (for bootloader) - portable
      * shortcuts on the desktop and in the Start menu, an item in «Installed applications»
    Restart = update (already downloaded again does not download).
#>
param([string]$InstallDir = "")

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
try { $Host.UI.RawUI.WindowTitle = 'ECHOES — installation' } catch {}
try { $Host.UI.RawUI.BackgroundColor = 'Black'; $Host.UI.RawUI.ForegroundColor = 'Gray' } catch {}
try {
    $raw = $Host.UI.RawUI
    $w = [Math]::Min(100, $raw.MaxPhysicalWindowSize.Width)
    if ($raw.BufferSize.Width -lt $w) { $raw.BufferSize = New-Object Management.Automation.Host.Size($w, 3000) }
    $raw.WindowSize = New-Object Management.Automation.Host.Size($w, [Math]::Min(42, $raw.MaxPhysicalWindowSize.Height))
} catch {}
Clear-Host

. (Join-Path $PSScriptRoot 'launcher.ps1')
. (Join-Path $PSScriptRoot 'downloads.ps1')

$APP_NAME    = 'ECHOES'
$APP_VERSION = '1.0'
$SRC_ROOT    = Split-Path -Parent $PSScriptRoot          # folder ECHOES_Setup
$SRC_APP     = Join-Path $SRC_ROOT 'app'
$sourceVersion = Join-Path $SRC_APP 'version.txt'
if (Test-Path -LiteralPath $sourceVersion) { $APP_VERSION = (Get-Content -LiteralPath $sourceVersion -Raw).Trim() }
if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA 'Programs\ECHOES' }

$PY_URLS = @(
    'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip',
    'https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip',
    'https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip'
)
$GETPIP_URLS = @('https://bootstrap.pypa.io/get-pip.py', 'https://bootstrap.pypa.io/pip/get-pip.py')
$VLC_URLS = @(
    'https://download.videolan.org/pub/videolan/vlc/3.0.21/win64/vlc-3.0.21-win64.zip',
    'https://get.videolan.org/vlc/3.0.21/win64/vlc-3.0.21-win64.zip',
    'https://download.videolan.org/pub/videolan/vlc/3.0.20/win64/vlc-3.0.20-win64.zip'
)
# required - without them the player will not start
$PKG_CORE  = @('PyQt6', 'python-vlc', 'numpy', 'scipy', 'mutagen', 'requests')
# всё остальное — тексты, загрузчик, онлайн-поиск, Discord, GIF
$PKG_EXTRA = @('yt-dlp', 'ytmusicapi', 'syncedlyrics', 'beautifulsoup4', 'lyricsgenius', 'Pillow', 'pypresence', 'sounddevice', 'pycryptodomex', 'websockets', 'av',
               'winrt-runtime', 'winrt-Windows.Foundation', 'winrt-Windows.Foundation.Collections', 'winrt-Windows.Media', 'winrt-Windows.Media.Playback', 'winrt-Windows.Storage', 'winrt-Windows.Storage.Streams')
$PKG_SPOT  = @('spotdl')

$TOTAL_STEPS = 7

# ═══════════════════════════════ registration ═══════════════════════════════ #

function Show-Logo {
    $logo = @(
        '   ███████╗ ██████╗██╗  ██╗ ██████╗ ███████╗███████╗',
        '   ██╔════╝██╔════╝██║  ██║██╔═══██╗██╔════╝██╔════╝',
        '   █████╗  ██║     ███████║██║   ██║█████╗  ███████╗',
        '   ██╔══╝  ██║     ██╔══██║██║   ██║██╔══╝  ╚════██║',
        '   ███████╗╚██████╗██║  ██║╚██████╔╝███████╗███████║',
        '   ╚══════╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝'
    )
    $cols = @('Yellow', 'Yellow', 'Yellow', 'DarkYellow', 'DarkYellow', 'DarkGray')
    Write-Host ''
    for ($i = 0; $i -lt $logo.Count; $i++) { Write-Host $logo[$i] -ForegroundColor $cols[$i] }
    Write-Host ''
    Write-Host '   music player  ·  ' -NoNewline -ForegroundColor Gray
    Write-Host "installer v$APP_VERSION" -ForegroundColor DarkYellow
    Write-Host '   ─────────────────────────────────────────────────────────' -ForegroundColor DarkGray
    Write-Host ''
}

function Step([int]$n, [string]$text) {
    Write-Host ''
    Write-Host "  [$n/$TOTAL_STEPS] " -NoNewline -ForegroundColor Black -BackgroundColor Yellow
    Write-Host " $text" -ForegroundColor White
}
function Ok([string]$t)   { Write-Host "      √ $t" -ForegroundColor Green }
function Info([string]$t) { Write-Host "      · $t" -ForegroundColor DarkGray }
function Warn([string]$t) { Write-Host "      ! $t" -ForegroundColor Yellow }
function Bad([string]$t)  { Write-Host "      × $t" -ForegroundColor Red }

function Show-Bar([long]$done, $total) {
    $mb = '{0:N1}' -f ($done / 1MB)
    if ($total -and $total -gt 0) {
        $pct = [Math]::Min(100, [int](100 * $done / $total))
        $fill = [int]($pct / 4)
        $bar = ('█' * $fill) + ('░' * (25 - $fill))
        $tot = '{0:N1}' -f ($total / 1MB)
        $line = "      $bar $pct%  $mb / $tot MB   "
    } else {
        $line = "      downloaded $mb MB…   "
    }
    [Console]::Write("`r$line")
}

function Fail([string]$msg) {
    Write-Host ''
    Write-Host '  ╔══════════════════════════════════════════════════════╗' -ForegroundColor Red
    Write-Host '  ║   Installation is not complete                             ║' -ForegroundColor Red
    Write-Host '  ╚══════════════════════════════════════════════════════╝' -ForegroundColor Red
    Write-Host ''
    Write-Host "  $msg" -ForegroundColor White
    Write-Host ''
    Write-Host '  What can you do:' -ForegroundColor Gray
    Write-Host '   1. Check your connection and run the installer again.' -ForegroundColor Gray
    Write-Host '      What has already been downloaded will not be downloaded again.' -ForegroundColor Gray
    Write-Host '   2. Temporarily disable VPN / proxies, if any.' -ForegroundColor Gray
    if ($script:LogFile) { Write-Host "   3. Detailed log: $script:LogFile" -ForegroundColor Gray }
    Write-Host ''
    try { Stop-Transcript | Out-Null } catch {}
    Read-Host '  Click Enter, to close'
    exit 1
}

# ═══════════════════════════════ utilities ═══════════════════════════════ #

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Expand-Zip([string]$Zip, [string]$To) {
    if (Test-Path $To) { Remove-Item $To -Recurse -Force -ErrorAction SilentlyContinue }
    New-Item -ItemType Directory -Path $To -Force | Out-Null
    [IO.Compression.ZipFile]::ExtractToDirectory($Zip, $To)
}

function Invoke-Native([string]$Exe, [string[]]$Arguments, [switch]$ShowPip) {
    # pip writes warnings to stderr — in PowerShell 5 this should not be considered a fall
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $line = "$_"
            if ($script:LogFile) { Add-Content -Path $script:LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue }
            if ($ShowPip) {
                if ($line -match '^\s*Collecting (\S+)') { Info "loading $($Matches[1])" }
                elseif ($line -match '^Successfully installed') { Ok 'installed' }
                elseif ($line -match '^(ERROR|error):') { Bad $line.Trim() }
            }
        }
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $old
    }
}

function Stop-Running {
    try {
        Get-Process -Name pythonw, python -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -and $_.Path.StartsWith($InstallDir, [StringComparison]::OrdinalIgnoreCase) } |
            ForEach-Object { Warn 'closing the running one ECHOES…'; $_ | Stop-Process -Force; Start-Sleep 1 }
    } catch {}
}

function New-Shortcut([string]$Path, [string]$Target, [string]$Arguments, [string]$WorkDir, [string]$Icon, [string]$Desc) {
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($Path)
    $s.TargetPath = $Target
    $s.Arguments = $Arguments
    $s.WorkingDirectory = $WorkDir
    $s.IconLocation = "$Icon,0"
    $s.Description = $Desc
    $s.Save()
}

# ═══════════════════════════════ installation ═══════════════════════════════ #

Show-Logo

if (-not [Environment]::Is64BitOperatingSystem) {
    Fail 'Need 64-bit Windows 10 or 11. On a 32-bit system ECHOES doesn′t work.'
}
if (-not (Test-Path (Join-Path $SRC_APP 'main.py'))) {
    Fail "Folder not found app next to the installer.`n  Unpack the archive ECHOES_Setup.zip ENTIRELY and run «INSTALL ECHOES.bat» from the unpacked folder."
}

Write-Host '   Where to install:  ' -NoNewline -ForegroundColor Gray
Write-Host $InstallDir -ForegroundColor White
Write-Host '   Needed ~1 GB of space and internet. No administrator rights needed.' -ForegroundColor DarkGray
Write-Host ''
$ans = Read-Host '   Enter — install here, or paste another path'
if ($ans -and $ans.Trim()) {
    $InstallDir = $ans.Trim().Trim('"')
    if (-not ($InstallDir -match 'ECHOES\\?$')) { $InstallDir = Join-Path $InstallDir 'ECHOES' }
}

try {
    $InstallDir = (New-Item -ItemType Directory -Path $InstallDir -Force).FullName
} catch {
    Fail "Failed to create folder $InstallDir. Select another (for example, on disk D:)."
}
$script:LogFile = Join-Path $InstallDir 'setup.log'
try { Start-Transcript -Path (Join-Path $InstallDir 'setup-transcript.log') -Force | Out-Null } catch {}
"=== ECHOES setup $(Get-Date) ===" | Set-Content -Path $script:LogFile -Encoding UTF8

$TMP = Join-Path $InstallDir '_download'
New-Item -ItemType Directory -Path $TMP -Force | Out-Null
$PY_DIR  = Join-Path $InstallDir 'python'
$APP_DIR = Join-Path $InstallDir 'app'
$VLC_DIR = Join-Path $InstallDir 'vlc'
$FF_DIR  = Join-Path $InstallDir 'ffmpeg'
$PY      = Join-Path $PY_DIR 'python.exe'
$PYW     = Join-Path $PY_DIR 'pythonw.exe'

# disk space
try {
    $drive = (Get-Item $InstallDir).PSDrive
    $freeGB = [Math]::Round($drive.Free / 1GB, 1)
    if ($freeGB -lt 1.2) { Warn "Low disk space on $($drive.Name): $freeGB GB available" }
} catch {}

$launcherSource = Get-EchoesLauncher $SRC_ROOT
$vlcZip = Join-Path $TMP 'vlc.zip'
$vlcDownload = $null
$pipDownload = $null
$pipBootstrap = Join-Path $TMP 'get-pip.py'
if (-not (Test-Path $PY)) {
    $pipDownload = Start-EchoesDownload $GETPIP_URLS $pipBootstrap
}
if (-not (Test-Path (Join-Path $VLC_DIR 'libvlc.dll'))) {
    $vlcDownload = Start-EchoesDownload $VLC_URLS $vlcZip
}

$ffmpegStarted = $false
if (-not ((Test-Path (Join-Path $FF_DIR 'ffmpeg.exe')) -and (Test-Path (Join-Path $FF_DIR 'ffprobe.exe')))) {
    try {
        $helper = Join-Path $PSScriptRoot 'ffmpeg.ps1'
        Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -WindowStyle Hidden -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $helper),
            '-InstallDir', ('"{0}"' -f $InstallDir)
        )
        $ffmpegStarted = $true
    } catch { Warn 'Could not start FFmpeg background setup' }
}

# ── 1. player files ───────────────────────────────────────────────────────
Step 1 'Copying player files'
Stop-Running
New-Item -ItemType Directory -Path $APP_DIR -Force | Out-Null
Get-ChildItem -Path $SRC_APP -File | ForEach-Object {
    Copy-Item $_.FullName -Destination $APP_DIR -Force
}
foreach ($assetFolder in @('assets', 'discord_assets', 'dsl_themes', 'montage_native', 'sounds')) {
    $assetSource = Join-Path $SRC_APP $assetFolder
    if (Test-Path -LiteralPath $assetSource) {
        $assetTarget = Join-Path $APP_DIR $assetFolder
        New-Item -ItemType Directory -Path $assetTarget -Force | Out-Null
        Get-ChildItem -LiteralPath $assetSource | Copy-Item -Destination $assetTarget -Recurse -Force
    }
}
Get-ChildItem -Path $APP_DIR -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
Remove-Item (Join-Path $APP_DIR '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $PSScriptRoot 'uninstall.en.ps1') -Destination (Join-Path $InstallDir 'uninstall.ps1') -Force
Ok "player files → $APP_DIR"

# ── 2. Python ─────────────────────────────────────────────────────────────
Step 2 'Python (your own, separate - other versions on the computer are not touched)'
if ((Test-Path $PY) -and (Test-Path $PYW)) {
    Ok 'already installed'
} else {
    $zip = Join-Path $TMP 'python.zip'
    if (-not (Get-File $PY_URLS $zip)) { Fail 'Failed to download Python s python.org.' }
    Expand-Zip $zip $PY_DIR
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Ok 'Python unpacked'
}
# path to the player and site-packages — in built-in Python specified by file ._pth
$pth = Get-ChildItem -Path $PY_DIR -Filter 'python3*._pth' | Select-Object -First 1
if (-not $pth) { Fail 'Python extraction failed (missing ._pth file). Remove the private Python folder and retry.' }
$zipName = ($pth.BaseName) + '.zip'
$pthText = "$zipName`r`n.`r`n..\app`r`nLib\site-packages`r`nimport site`r`n"
[IO.File]::WriteAllText($pth.FullName, $pthText, (New-Object Text.ASCIIEncoding))

# ── 3. pip ────────────────────────────────────────────────────────────────
Step 3 'Package Manager pip'
$code = Invoke-Native $PY @('-m', 'pip', '--version')
if ($code -eq 0) {
    Ok 'already there'
} else {
    $gp = $pipBootstrap
    if (-not (Receive-EchoesDownload $pipDownload $GETPIP_URLS $gp)) { Fail 'Installer download failed pip.' }
    $code = Invoke-Native $PY @($gp, '--no-compile', '--no-warn-script-location', '--disable-pip-version-check')
    if ($code -ne 0) { Fail 'pip not installed. Details - in the magazine.' }
    Ok 'pip installed'
}

# ── 4. libraries ─────────────────────────────────────────────────────────
Step 4 'Installing Python libraries'
$pipBase = @('-m', 'pip', 'install', '--upgrade', '--prefer-binary', '--no-compile', '--no-warn-script-location',
             '--disable-pip-version-check', '--timeout', '60', '--retries', '5')
$constraints = Join-Path $PSScriptRoot 'constraints.txt'
if (Test-Path -LiteralPath $constraints) { $pipBase += @('-c', $constraints) }
# Resolve the core and feature dependencies in one pass. If an optional wheel is
# unavailable, still install a working player and try the other features separately.
if ((Invoke-Native $PY ($pipBase + $PKG_CORE + $PKG_EXTRA) -ShowPip) -eq 0) {
    Ok 'Python libraries installed'
} else {
    $ok = $false
    for ($i = 1; $i -le 3 -and -not $ok; $i++) {
        if ($i -gt 1) { Warn "one more try ($i/3)…"; Start-Sleep 3 }
        $ok = ((Invoke-Native $PY ($pipBase + $PKG_CORE) -ShowPip) -eq 0)
    }
    if (-not $ok) { Fail 'Failed to install core libraries (PyQt6, numpy, …).' }
    Ok 'main libraries are ready'

    $failed = @()
    if ((Invoke-Native $PY ($pipBase + $PKG_EXTRA) -ShowPip) -ne 0) {
        foreach ($p in $PKG_EXTRA) {
            if ((Invoke-Native $PY ($pipBase + @($p)) -ShowPip) -ne 0) { $failed += $p }
        }
    }
    if ($failed.Count) { Warn "not installed: $($failed -join ', ') — these functions will not be available" }
    else { Ok 'texts, downloader, online search, Discord — ready' }
}

$spotify = Read-Host '   Add the optional Spotify downloader (spotdl)? [y/N]'
if ($spotify -match '^(y|yes)$') {
    Info 'Spotify-bootloader (optional))…'
    if ((Invoke-Native $PY ($pipBase + $PKG_SPOT) -ShowPip) -ne 0) { Warn 'spotdl didn′t get up - import from Spotify still works through the built-in utility' }
}

# ── 5. VLC ────────────────────────────────────────────────────────────────
Step 5 'VLC — playback engine'
if (Test-Path (Join-Path $VLC_DIR 'libvlc.dll')) {
    Ok 'already installed'
} else {
    $zip = $vlcZip
    if (-not (Receive-EchoesDownload $vlcDownload $VLC_URLS $zip)) {
        if (Test-Path 'C:\Program Files\VideoLAN\VLC\libvlc.dll') {
            Warn 'I couldn′t download it, but it′s already on my computer VLC — the player will take it'
        } else {
            Fail 'Failed to download VLC s videolan.org.'
        }
    } else {
        Info 'unpacking…'
        $tmpV = Join-Path $TMP 'vlc_x'
        Expand-Zip $zip $tmpV
        $inner = Get-ChildItem -Path $tmpV -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'libvlc.dll') } | Select-Object -First 1
        if (-not $inner) { Fail 'Invalid VLC archive. Run the installer again.' }
        if (Test-Path $VLC_DIR) { Remove-Item $VLC_DIR -Recurse -Force }
        Move-Item $inner.FullName $VLC_DIR
        Remove-Item $tmpV -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        Ok 'VLC ready'
    }
}
# plugin cache: no plugins.dat VLC every time you start the player it loads everything ~365 plugins (slow start)
$cacheGen = Join-Path $VLC_DIR 'vlc-cache-gen.exe'
if ((Test-Path $cacheGen) -and -not (Test-Path (Join-Path $VLC_DIR 'plugins\plugins.dat'))) {
    & $cacheGen (Join-Path $VLC_DIR 'plugins') 2>&1 | Out-Null
}

# FFmpeg is used by optional features; playback is ready once VLC and Python are installed.
Step 6 'ffmpeg — preparing the download tools'
if ((Test-Path (Join-Path $FF_DIR 'ffmpeg.exe')) -and (Test-Path (Join-Path $FF_DIR 'ffprobe.exe'))) {
    Ok 'FFmpeg'
} elseif ($ffmpegStarted) {
    Info 'The downloader and effects will be ready when the FFmpeg background setup finishes'
}

# ── 7. shortcuts ─────────────────────────────────────────────────────────────
Step 7 'Shortcuts and registration in Windows'
$main = Join-Path $APP_DIR 'main.py'
$ico  = Join-Path $APP_DIR 'icon.ico'
$psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$uninstArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallDir 'uninstall.ps1')`""
# GUI launcher is optional for older distributions; keep the direct player shortcut too.
$launcherTarget = Join-Path $InstallDir 'ECHOES Launcher.exe'
if ($launcherSource) {
    try {
        Install-EchoesLauncher $launcherSource $InstallDir
        New-Shortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ECHOES Launcher.lnk') $launcherTarget '' $InstallDir $ico 'ECHOES — launch and updates'
        $launcherMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'ECHOES'
        New-Item -ItemType Directory -Path $launcherMenu -Force | Out-Null
        New-Shortcut (Join-Path $launcherMenu 'ECHOES Launcher.lnk') $launcherTarget '' $InstallDir $ico 'ECHOES — launch and updates'
    } catch { Warn "launcher not copied: $($_.Exception.Message)" }
}
try {
    $desk = [Environment]::GetFolderPath('Desktop')
    New-Shortcut (Join-Path $desk 'ECHOES.lnk') $PYW "`"$main`"" $APP_DIR $ico 'ECHOES — music player'
    Ok 'desktop shortcut'
} catch { Warn "desktop shortcut not created: $($_.Exception.Message)" }
try {
    $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'ECHOES'
    New-Item -ItemType Directory -Path $menu -Force | Out-Null
    New-Shortcut (Join-Path $menu 'ECHOES.lnk') $PYW "`"$main`"" $APP_DIR $ico 'ECHOES — music player'
    New-Shortcut (Join-Path $menu 'Delete ECHOES.lnk') $psExe $uninstArgs $InstallDir $ico 'Delete ECHOES'
    Ok 'start menu»'
} catch { Warn "Start menu shortcut not created: $($_.Exception.Message)" }
try {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ECHOES'
    New-Item -Path $key -Force | Out-Null
    $size = 0
    try { $size = [int]((Get-ChildItem $InstallDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1KB) } catch {}
    $props = @{
        DisplayName = 'ECHOES'; DisplayVersion = $APP_VERSION; Publisher = 'ECHOES';
        DisplayIcon = $ico; InstallLocation = $InstallDir;
        UninstallString = "`"$psExe`" $uninstArgs"; NoModify = 1; NoRepair = 1; EstimatedSize = $size
    }
    foreach ($k in $props.Keys) {
        $type = if ($props[$k] -is [int]) { 'DWord' } else { 'String' }
        New-ItemProperty -Path $key -Name $k -Value $props[$k] -PropertyType $type -Force | Out-Null
    }
    Ok 'ECHOES appeared in «Installed applications» (it is also deleted from there))'
} catch { Warn 'could not register in the list of programs' }

Remove-Item $TMP -Recurse -Force -ErrorAction SilentlyContinue
try { Stop-Transcript | Out-Null } catch {}

# ── done ────────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '  ╔══════════════════════════════════════════════════════╗' -ForegroundColor Green
Write-Host '  ║                                                      ║' -ForegroundColor Green
Write-Host '  ║          ECHOES  INSTALLED - EVERYTHING IS READY  ♪        ║' -ForegroundColor Green
Write-Host '  ║                                                      ║' -ForegroundColor Green
Write-Host '  ╚══════════════════════════════════════════════════════╝' -ForegroundColor Green
Write-Host ''
Write-Host '   Launch via shortcut ' -NoNewline -ForegroundColor Gray
Write-Host 'ECHOES' -NoNewline -ForegroundColor Yellow
Write-Host ' on your desktop or in the Start menu.' -ForegroundColor Gray
Write-Host '   Folder ECHOES_Setup now you can delete.' -ForegroundColor DarkGray
Write-Host ''
$go = Read-Host '   Start ECHOES now? [Enter = yes / n = no]'
if ($go -notmatch '^(n|n|no|no)$') {
    Start-Process -FilePath $PYW -ArgumentList "`"$main`"" -WorkingDirectory $APP_DIR
}
exit 0
