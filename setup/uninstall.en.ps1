#Requires -Version 5.1
# ECHOES — deletion. Placed by the installer in the program folder.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { $Host.UI.RawUI.WindowTitle = 'ECHOES — destroy' } catch {}
try { $Host.UI.RawUI.BackgroundColor = 'Black' } catch {}
Clear-Host

$InstallDir = $PSScriptRoot
$DataDir    = Join-Path $env:USERPROFILE 'Echoes'
if (-not (Test-Path $DataDir)) { $DataDir = Join-Path $env:USERPROFILE '.neon_player' }   # ещё не перенесены

Write-Host ''
Write-Host '   ECHOES — destroy' -ForegroundColor Yellow
Write-Host '   ─────────────────────────────────────────' -ForegroundColor DarkGray
Write-Host "   Program: $InstallDir" -ForegroundColor Gray
Write-Host ''
$a = Read-Host '   Delete ECHOES? [y — yes / Enter — cancellation]'
if ($a -notmatch '^(y|d|yes|yes)$') { Write-Host '   Cancelled.' -ForegroundColor DarkGray; Start-Sleep 1; exit 0 }

$keepData = $true
if (Test-Path $DataDir) {
    Write-Host ''
    Write-Host '   Your playlists, library and settings are separate:' -ForegroundColor Gray
    Write-Host "   $DataDir" -ForegroundColor Gray
    $b = Read-Host '   Delete them too? [y — delete / Enter — leave]'
    if ($b -match '^(y|d|yes|yes)$') { $keepData = $false }
}

# close the running player
$runtime = Join-Path $InstallDir 'python'
$targets = @('Echoes.exe', 'pythonw.exe', 'python.exe') | ForEach-Object { Join-Path $runtime $_ }
Get-Process -Name Echoes, pythonw, python -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -in $targets } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ECHOES.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ECHOES Launcher.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'ECHOES') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'NeonPlayer.vbs') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Startup')) 'ECHOES.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\ECHOES' -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item 'HKCU:\Software\Classes\AppUserModelId\echoes.player' -Recurse -Force -ErrorAction SilentlyContinue
if (-not $keepData) { Remove-Item $DataDir -Recurse -Force -ErrorAction SilentlyContinue }

Set-Location $env:TEMP
Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path $InstallDir) {
    # Some files may have been occupied - we clean them up after exiting
    Start-Process -WindowStyle Hidden -FilePath "$env:SystemRoot\System32\cmd.exe" `
        -ArgumentList "/c timeout /t 3 >nul & rmdir /s /q `"$InstallDir`""
}

Write-Host ''
Write-Host '   √ ECHOES deleted.' -ForegroundColor Green
if ($keepData) { Write-Host '     Your playlists and settings are saved - everything will come back when you install it again.' -ForegroundColor DarkGray }
Write-Host ''
Start-Sleep 3
