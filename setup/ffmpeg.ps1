#Requires -Version 5.1
param([Parameter(Mandatory = $true)][string]$InstallDir)

$ErrorActionPreference = 'Stop'
$ffmpeg = Join-Path $InstallDir 'ffmpeg'
$log = Join-Path $InstallDir 'ffmpeg-setup.log'
$urls = @(
    'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
    'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
    'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
)

function Info([string]$Text) { Add-Content -LiteralPath $log -Value $Text -Encoding UTF8 }
function Warn([string]$Text) { Info $Text }
function Ok([string]$Text) { Info $Text }
function Show-Bar([long]$Done, $Total) {}
. (Join-Path $PSScriptRoot 'downloads.ps1')

# Setup can be opened again while the first FFmpeg download is still in progress.
try {
    $lock = [IO.File]::Open((Join-Path $InstallDir 'ffmpeg-setup.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
} catch [IO.IOException] {
    exit 0
}
$stage = Join-Path $InstallDir ('.ffmpeg-' + [Guid]::NewGuid().ToString('N'))
try {
    if ((Test-Path (Join-Path $ffmpeg 'ffmpeg.exe')) -and (Test-Path (Join-Path $ffmpeg 'ffprobe.exe'))) { exit 0 }
    Info 'Preparing FFmpeg'
    New-Item -ItemType Directory -Path $stage | Out-Null
    $zip = Join-Path $stage 'ffmpeg.zip'
    if (-not (Get-File $urls $zip)) { throw 'Could not download FFmpeg' }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($zip)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName -match '(^|/)bin/(ffmpeg|ffprobe)\.exe$') {
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $stage $entry.Name), $true)
            }
        }
    } finally { $archive.Dispose() }

    foreach ($file in @('ffprobe.exe', 'ffmpeg.exe')) {
        if ((Get-Item -LiteralPath (Join-Path $stage $file)).Length -eq 0) { throw "Invalid $file" }
    }
    New-Item -ItemType Directory -Path $ffmpeg -Force | Out-Null
    foreach ($file in @('ffprobe.exe', 'ffmpeg.exe')) {
        $source = Join-Path $stage $file
        $target = Join-Path $ffmpeg $file
        if (Test-Path -LiteralPath $target) {
            [IO.File]::Replace($source, $target, (Join-Path $stage "$file.previous"))
        } else {
            [IO.File]::Move($source, $target)
        }
    }
    Info 'FFmpeg ready'
} catch {
    Warn $_.Exception.Message
    exit 1
} finally {
    $lock.Dispose()
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
